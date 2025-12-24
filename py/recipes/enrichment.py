import logging
import json
import re
import os
from typing import Any, Dict, Optional
from .merger import GenParamsMerger
from .base import RecipeMetadataParser
from ..services.metadata_service import get_default_metadata_provider

logger = logging.getLogger(__name__)

class RecipeEnricher:
    """Service to enrich recipe metadata from multiple sources (Civitai, Embedded, User)."""

    @staticmethod
    async def enrich_recipe(
        recipe: Dict[str, Any],
        civitai_client: Any,
        request_params: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Enrich a recipe dictionary in-place with metadata from Civitai and embedded params.
        
        Args:
            recipe: The recipe dictionary to enrich. Must have 'gen_params' initialized.
            civitai_client: Authenticated Civitai client instance.
            request_params: (Optional) Parameters from a user request (e.g. import).
            
        Returns:
            bool: True if the recipe was modified, False otherwise.
        """
        updated = False
        gen_params = recipe.get("gen_params", {})
        
        # 1. Fetch Civitai Info if available
        civitai_meta = None
        model_version_id = None
        
        source_url = recipe.get("source_url") or recipe.get("source_path", "")
        
        # Check if it's a Civitai image URL
        image_id_match = re.search(r'civitai\.com/images/(\d+)', str(source_url))
        if image_id_match:
            image_id = image_id_match.group(1)
            try:
                image_info = await civitai_client.get_image_info(image_id)
                if image_info:
                    # Handle nested meta often found in Civitai API responses
                    raw_meta = image_info.get("meta")
                    if isinstance(raw_meta, dict):
                        if "meta" in raw_meta and isinstance(raw_meta["meta"], dict):
                            civitai_meta = raw_meta["meta"]
                        else:
                            civitai_meta = raw_meta
                    
                    model_version_id = image_info.get("modelVersionId")
                    
                    # If not at top level, check resources in meta
                    if not model_version_id and civitai_meta:
                        resources = civitai_meta.get("civitaiResources", [])
                        for res in resources:
                            if res.get("type") == "checkpoint":
                                model_version_id = res.get("modelVersionId")
                                break
            except Exception as e:
                logger.warning(f"Failed to fetch Civitai image info: {e}")

        # 2. Merge Parameters
        # Priority: request_params > civitai_meta > embedded (existing gen_params)
        new_gen_params = GenParamsMerger.merge(
            request_params=request_params,
            civitai_meta=civitai_meta,
            embedded_metadata=gen_params
        )
        
        if new_gen_params != gen_params:
            recipe["gen_params"] = new_gen_params
            updated = True
        
        # 3. Checkpoint Enrichment
        # If we have a checkpoint entry, or we can find one
        # Use 'id' (from Civitai version) as a marker that it's been enriched
        checkpoint_entry = recipe.get("checkpoint")
        has_full_checkpoint = checkpoint_entry and checkpoint_entry.get("name") and checkpoint_entry.get("id")
        
        if not has_full_checkpoint:
            # Helper to look up values in priority order
            def start_lookup(keys):
                for source in [request_params, civitai_meta, gen_params]:
                    if source:
                        if isinstance(keys, list):
                            for k in keys:
                                if k in source: return source[k]
                        else:
                            if keys in source: return source[keys]
                return None

            target_version_id = model_version_id or start_lookup("modelVersionId")
            
            # Also check existing checkpoint entry
            if not target_version_id and checkpoint_entry:
                target_version_id = checkpoint_entry.get("modelVersionId") or checkpoint_entry.get("id")
            
            # Check for version ID in resources (which might be a string in gen_params)
            if not target_version_id:
                # Look in all sources for "Civitai resources"
                resources_val = start_lookup(["Civitai resources", "civitai_resources", "resources"])
                if resources_val:
                    target_version_id = RecipeEnricher._extract_version_id_from_resources({"Civitai resources": resources_val})
            
            target_hash = start_lookup(["Model hash", "checkpoint_hash", "hashes"])
            if not target_hash and checkpoint_entry:
                target_hash = checkpoint_entry.get("hash") or checkpoint_entry.get("model_hash")
            
            # Look for 'Model' which sometimes is the hash or name
            model_val = start_lookup("Model")

            # Look for Checkpoint name fallback
            checkpoint_val = checkpoint_entry.get("name") if checkpoint_entry else None
            if not checkpoint_val:
                checkpoint_val = start_lookup(["Checkpoint", "checkpoint"])

            checkpoint_updated = await RecipeEnricher._resolve_and_populate_checkpoint(
                recipe, target_version_id, target_hash, model_val, checkpoint_val
            )
            if checkpoint_updated:
                # Sync to gen_params for consistency with legacy usage
                if "gen_params" not in recipe:
                    recipe["gen_params"] = {}
                recipe["gen_params"]["checkpoint"] = recipe["checkpoint"]
                updated = True
        else:
            # Even if we have a checkpoint, ensure it is synced to gen_params if missing there
            if "checkpoint" in recipe and recipe["checkpoint"]:
                if "gen_params" not in recipe:
                    recipe["gen_params"] = {}
                if "checkpoint" not in recipe["gen_params"]:
                    recipe["gen_params"]["checkpoint"] = recipe["checkpoint"]
                    # We don't necessarily mark 'updated=True' just for this sync if the rest is the same,
                    # but it's safer to ensure it's there.
                    updated = True
        # If base_model is empty or very generic, try to use what we found in checkpoint
        current_base_model = recipe.get("base_model")
        checkpoint_after = recipe.get("checkpoint")
        if checkpoint_after and checkpoint_after.get("baseModel"):
            resolved_base_model = checkpoint_after["baseModel"]
            # Update if empty OR if it matches our generic prefix but is less specific
            is_generic = not current_base_model or current_base_model.lower() in ["flux", "sdxl", "sd15"]
            if is_generic and resolved_base_model != current_base_model:
                recipe["base_model"] = resolved_base_model
                updated = True

        return updated
        
    @staticmethod
    def _extract_version_id_from_resources(gen_params: Dict[str, Any]) -> Optional[Any]:
        """Try to find modelVersionId in Civitai resources parameter."""
        civitai_resources_raw = gen_params.get("Civitai resources")
        if not civitai_resources_raw:
            return None
            
        resources_list = None
        if isinstance(civitai_resources_raw, str):
            try:
                resources_list = json.loads(civitai_resources_raw)
            except Exception:
                pass
        elif isinstance(civitai_resources_raw, list):
            resources_list = civitai_resources_raw
            
        if isinstance(resources_list, list):
            for res in resources_list:
                if res.get("type") == "checkpoint":
                    return res.get("modelVersionId")
        return None

    @staticmethod
    async def _resolve_and_populate_checkpoint(
        recipe: Dict[str, Any], 
        target_version_id: Optional[Any], 
        target_hash: Optional[str],
        model_val: Optional[str],
        checkpoint_val: Optional[str]
    ) -> bool:
        """Find checkpoint metadata and populate it in the recipe."""
        metadata_provider = await get_default_metadata_provider()
        civitai_info = None
        
        if target_version_id:
            civitai_info = await metadata_provider.get_model_version_info(str(target_version_id))
        elif target_hash:
            civitai_info = await metadata_provider.get_model_by_hash(target_hash)
        else:
            # Look for 'Model' which sometimes is the hash or name
            if model_val and len(model_val) == 10: # Likely a short hash
                civitai_info = await metadata_provider.get_model_by_hash(model_val)
                
        if civitai_info and not (isinstance(civitai_info, tuple) and civitai_info[1] == "Model not found"):
            # If we already have a partial checkpoint, use it as base
            existing_cp = recipe.get("checkpoint")
            if existing_cp is None:
                existing_cp = {}
            checkpoint_data = await RecipeMetadataParser.populate_checkpoint_from_civitai(existing_cp, civitai_info)
            recipe["checkpoint"] = checkpoint_data
            
            # Ensure the modelVersionId is stored if we found it
            if target_version_id and "modelVersionId" not in recipe["checkpoint"]:
                recipe["checkpoint"]["modelVersionId"] = int(target_version_id)
            return True
        else:
            # Fallback to name extraction if we don't already have one
            existing_cp = recipe.get("checkpoint")
            if not existing_cp or not existing_cp.get("name"):
                cp_name = checkpoint_val
                if cp_name:
                    recipe["checkpoint"] = {
                        "type": "checkpoint",
                        "name": cp_name,
                        "modelName": cp_name,
                        "file_name": os.path.splitext(cp_name)[0]
                    }
                    return True
                
        return False
