import os
import logging
from typing import Dict, List, Optional

from .base_model_service import BaseModelService
from ..utils.models import LoraMetadata
from ..config import config

logger = logging.getLogger(__name__)


class LoraService(BaseModelService):
    """LoRA-specific service implementation"""

    def __init__(self, scanner, update_service=None):
        """Initialize LoRA service

        Args:
            scanner: LoRA scanner instance
            update_service: Optional service for remote update tracking.
        """
        super().__init__("lora", scanner, LoraMetadata, update_service=update_service)

    async def format_response(self, lora_data: Dict) -> Dict:
        """Format LoRA data for API response"""
        return {
            "model_name": lora_data["model_name"],
            "file_name": lora_data["file_name"],
            "preview_url": config.get_preview_static_url(
                lora_data.get("preview_url", "")
            ),
            "preview_nsfw_level": lora_data.get("preview_nsfw_level", 0),
            "base_model": lora_data.get("base_model", ""),
            "folder": lora_data["folder"],
            "sha256": lora_data.get("sha256", ""),
            "file_path": lora_data["file_path"].replace(os.sep, "/"),
            "file_size": lora_data.get("size", 0),
            "modified": lora_data.get("modified", ""),
            "tags": lora_data.get("tags", []),
            "from_civitai": lora_data.get("from_civitai", True),
            "usage_count": lora_data.get("usage_count", 0),
            "usage_tips": lora_data.get("usage_tips", ""),
            "notes": lora_data.get("notes", ""),
            "favorite": lora_data.get("favorite", False),
            "update_available": bool(lora_data.get("update_available", False)),
            "civitai": self.filter_civitai_data(
                lora_data.get("civitai", {}), minimal=True
            ),
        }

    async def _apply_specific_filters(self, data: List[Dict], **kwargs) -> List[Dict]:
        """Apply LoRA-specific filters"""
        # Handle first_letter filter for LoRAs
        first_letter = kwargs.get("first_letter")
        if first_letter:
            data = self._filter_by_first_letter(data, first_letter)

        return data

    def _filter_by_first_letter(self, data: List[Dict], letter: str) -> List[Dict]:
        """Filter data by first letter of model name

        Special handling:
        - '#': Numbers (0-9)
        - '@': Special characters (not alphanumeric)
        - '漢': CJK characters
        """
        filtered_data = []

        for lora in data:
            model_name = lora.get("model_name", "")
            if not model_name:
                continue

            first_char = model_name[0].upper()

            if letter == "#" and first_char.isdigit():
                filtered_data.append(lora)
            elif letter == "@" and not first_char.isalnum():
                # Special characters (not alphanumeric)
                filtered_data.append(lora)
            elif letter == "漢" and self._is_cjk_character(first_char):
                # CJK characters
                filtered_data.append(lora)
            elif letter.upper() == first_char:
                # Regular alphabet matching
                filtered_data.append(lora)

        return filtered_data

    def _is_cjk_character(self, char: str) -> bool:
        """Check if character is a CJK character"""
        # Define Unicode ranges for CJK characters
        cjk_ranges = [
            (0x4E00, 0x9FFF),  # CJK Unified Ideographs
            (0x3400, 0x4DBF),  # CJK Unified Ideographs Extension A
            (0x20000, 0x2A6DF),  # CJK Unified Ideographs Extension B
            (0x2A700, 0x2B73F),  # CJK Unified Ideographs Extension C
            (0x2B740, 0x2B81F),  # CJK Unified Ideographs Extension D
            (0x2B820, 0x2CEAF),  # CJK Unified Ideographs Extension E
            (0x2CEB0, 0x2EBEF),  # CJK Unified Ideographs Extension F
            (0x30000, 0x3134F),  # CJK Unified Ideographs Extension G
            (0xF900, 0xFAFF),  # CJK Compatibility Ideographs
            (0x3300, 0x33FF),  # CJK Compatibility
            (0x3200, 0x32FF),  # Enclosed CJK Letters and Months
            (0x3100, 0x312F),  # Bopomofo
            (0x31A0, 0x31BF),  # Bopomofo Extended
            (0x3040, 0x309F),  # Hiragana
            (0x30A0, 0x30FF),  # Katakana
            (0x31F0, 0x31FF),  # Katakana Phonetic Extensions
            (0xAC00, 0xD7AF),  # Hangul Syllables
            (0x1100, 0x11FF),  # Hangul Jamo
            (0xA960, 0xA97F),  # Hangul Jamo Extended-A
            (0xD7B0, 0xD7FF),  # Hangul Jamo Extended-B
        ]

        code_point = ord(char)
        return any(start <= code_point <= end for start, end in cjk_ranges)

    # LoRA-specific methods
    async def get_letter_counts(self) -> Dict[str, int]:
        """Get count of LoRAs for each letter of the alphabet"""
        cache = await self.scanner.get_cached_data()
        data = cache.raw_data

        # Define letter categories
        letters = {
            "#": 0,  # Numbers
            "A": 0,
            "B": 0,
            "C": 0,
            "D": 0,
            "E": 0,
            "F": 0,
            "G": 0,
            "H": 0,
            "I": 0,
            "J": 0,
            "K": 0,
            "L": 0,
            "M": 0,
            "N": 0,
            "O": 0,
            "P": 0,
            "Q": 0,
            "R": 0,
            "S": 0,
            "T": 0,
            "U": 0,
            "V": 0,
            "W": 0,
            "X": 0,
            "Y": 0,
            "Z": 0,
            "@": 0,  # Special characters
            "漢": 0,  # CJK characters
        }

        # Count models for each letter
        for lora in data:
            model_name = lora.get("model_name", "")
            if not model_name:
                continue

            first_char = model_name[0].upper()

            if first_char.isdigit():
                letters["#"] += 1
            elif first_char in letters:
                letters[first_char] += 1
            elif self._is_cjk_character(first_char):
                letters["漢"] += 1
            elif not first_char.isalnum():
                letters["@"] += 1

        return letters

    async def get_lora_trigger_words(self, lora_name: str) -> List[str]:
        """Get trigger words for a specific LoRA file"""
        cache = await self.scanner.get_cached_data()

        for lora in cache.raw_data:
            if lora["file_name"] == lora_name:
                civitai_data = lora.get("civitai", {})
                return civitai_data.get("trainedWords", [])

        return []

    async def get_lora_usage_tips_by_relative_path(
        self, relative_path: str
    ) -> Optional[str]:
        """Get usage tips for a LoRA by its relative path"""
        cache = await self.scanner.get_cached_data()

        for lora in cache.raw_data:
            file_path = lora.get("file_path", "")
            if file_path:
                # Convert to forward slashes and extract relative path
                file_path_normalized = file_path.replace("\\", "/")
                relative_path = relative_path.replace("\\", "/")
                # Find the relative path part by looking for the relative_path in the full path
                if (
                    file_path_normalized.endswith(relative_path)
                    or relative_path in file_path_normalized
                ):
                    return lora.get("usage_tips", "")

        return None

    def find_duplicate_hashes(self) -> Dict:
        """Find LoRAs with duplicate SHA256 hashes"""
        return self.scanner._hash_index.get_duplicate_hashes()

    def find_duplicate_filenames(self) -> Dict:
        """Find LoRAs with conflicting filenames"""
        return self.scanner._hash_index.get_duplicate_filenames()

    async def get_random_loras(
        self,
        count: int,
        model_strength_min: float = 0.0,
        model_strength_max: float = 1.0,
        use_same_clip_strength: bool = True,
        clip_strength_min: float = 0.0,
        clip_strength_max: float = 1.0,
        locked_loras: Optional[List[Dict]] = None,
        pool_config: Optional[Dict] = None,
        count_mode: str = "fixed",
        count_min: int = 3,
        count_max: int = 7,
        use_recommended_strength: bool = False,
        recommended_strength_scale_min: float = 0.5,
        recommended_strength_scale_max: float = 1.0,
    ) -> List[Dict]:
        """
        Get random LoRAs with specified strength ranges.

        Args:
            count: Number of LoRAs to select (if count_mode='fixed')
            model_strength_min: Minimum model strength
            model_strength_max: Maximum model strength
            use_same_clip_strength: Whether to use same strength for clip
            clip_strength_min: Minimum clip strength
            clip_strength_max: Maximum clip strength
            locked_loras: List of locked LoRA dicts to preserve
            pool_config: Optional pool config for filtering
            count_mode: How to determine count ('fixed' or 'range')
            count_min: Minimum count for range mode
            count_max: Maximum count for range mode
            use_recommended_strength: Whether to use recommended strength from usage_tips
            recommended_strength_scale_min: Minimum scale factor for recommended strength
            recommended_strength_scale_max: Maximum scale factor for recommended strength

        Returns:
            List of LoRA dicts with randomized strengths
        """
        import random
        import json

        def get_recommended_strength(lora_data: Dict) -> Optional[float]:
            """Parse usage_tips JSON and extract recommended strength"""
            try:
                usage_tips = lora_data.get("usage_tips", "")
                if not usage_tips:
                    return None
                tips_data = json.loads(usage_tips)
                return tips_data.get("strength")
            except (json.JSONDecodeError, TypeError, AttributeError):
                return None

        def get_recommended_clip_strength(lora_data: Dict) -> Optional[float]:
            """Parse usage_tips JSON and extract recommended clip strength"""
            try:
                usage_tips = lora_data.get("usage_tips", "")
                if not usage_tips:
                    return None
                tips_data = json.loads(usage_tips)
                return tips_data.get("clipStrength")
            except (json.JSONDecodeError, TypeError, AttributeError):
                return None

        if locked_loras is None:
            locked_loras = []

        # Determine target count based on count_mode
        if count_mode == "fixed":
            target_count = count
        else:
            target_count = random.randint(count_min, count_max)

        # Get available loras from cache
        cache = await self.scanner.get_cached_data(force_refresh=False)
        available_loras = cache.raw_data if cache else []

        # Apply pool filters if provided
        if pool_config:
            available_loras = await self._apply_pool_filters(
                available_loras, pool_config
            )

        # Calculate slots needed (total - locked)
        locked_count = len(locked_loras)
        slots_needed = target_count - locked_count

        if slots_needed < 0:
            slots_needed = 0
            # Too many locked, trim to target
            locked_loras = locked_loras[:target_count]

        # Filter out locked LoRAs from available pool
        locked_names = {lora["name"] for lora in locked_loras}
        available_pool = [
            l for l in available_loras if l["file_name"] not in locked_names
        ]

        # Ensure we don't try to select more than available
        if slots_needed > len(available_pool):
            slots_needed = len(available_pool)

        # Random sample
        selected = []
        if slots_needed > 0:
            selected = random.sample(available_pool, slots_needed)

        # Generate random strengths for selected LoRAs
        result_loras = []
        for lora in selected:
            if use_recommended_strength:
                recommended_strength = get_recommended_strength(lora)
                if recommended_strength is not None:
                    scale = random.uniform(
                        recommended_strength_scale_min, recommended_strength_scale_max
                    )
                    model_str = round(recommended_strength * scale, 2)
                else:
                    model_str = round(
                        random.uniform(model_strength_min, model_strength_max), 2
                    )
            else:
                model_str = round(
                    random.uniform(model_strength_min, model_strength_max), 2
                )

            if use_same_clip_strength:
                clip_str = model_str
            elif use_recommended_strength:
                recommended_clip_strength = get_recommended_clip_strength(lora)
                if recommended_clip_strength is not None:
                    scale = random.uniform(
                        recommended_strength_scale_min, recommended_strength_scale_max
                    )
                    clip_str = round(recommended_clip_strength * scale, 2)
                else:
                    clip_str = round(
                        random.uniform(clip_strength_min, clip_strength_max), 2
                    )
            else:
                clip_str = round(
                    random.uniform(clip_strength_min, clip_strength_max), 2
                )

            result_loras.append(
                {
                    "name": lora["file_name"],
                    "strength": model_str,
                    "clipStrength": clip_str,
                    "active": True,
                    "expanded": abs(model_str - clip_str) > 0.001,
                    "locked": False,
                }
            )

        # Merge with locked LoRAs
        result_loras.extend(locked_loras)

        return result_loras

    async def _apply_pool_filters(
        self, available_loras: List[Dict], pool_config: Dict
    ) -> List[Dict]:
        """
        Apply pool_config filters to available LoRAs.

        Args:
            available_loras: List of all LoRA dicts
            pool_config: Dict with filter settings from LoRA Pool node

        Returns:
            Filtered list of LoRA dicts
        """
        from .model_query import FilterCriteria

        filter_section = pool_config

        # Extract filter parameters
        selected_base_models = filter_section.get("baseModels", [])
        tags_dict = filter_section.get("tags", {})
        include_tags = tags_dict.get("include", [])
        exclude_tags = tags_dict.get("exclude", [])
        folders_dict = filter_section.get("folders", {})
        include_folders = folders_dict.get("include", [])
        exclude_folders = folders_dict.get("exclude", [])
        license_dict = filter_section.get("license", {})
        no_credit_required = license_dict.get("noCreditRequired", False)
        allow_selling = license_dict.get("allowSelling", False)

        # Build tag filters dict
        tag_filters = {}
        for tag in include_tags:
            tag_filters[tag] = "include"
        for tag in exclude_tags:
            tag_filters[tag] = "exclude"

        # Build folder filter
        if include_folders or exclude_folders:
            filtered = []
            for lora in available_loras:
                folder = lora.get("folder", "")

                # Check exclude folders first
                excluded = False
                for exclude_folder in exclude_folders:
                    if folder.startswith(exclude_folder):
                        excluded = True
                        break

                if excluded:
                    continue

                # Check include folders
                if include_folders:
                    included = False
                    for include_folder in include_folders:
                        if folder.startswith(include_folder):
                            included = True
                            break
                    if not included:
                        continue

                filtered.append(lora)

            available_loras = filtered

        # Apply base model filter
        if selected_base_models:
            available_loras = [
                lora
                for lora in available_loras
                if lora.get("base_model") in selected_base_models
            ]

        # Apply tag filters
        if tag_filters:
            criteria = FilterCriteria(tags=tag_filters)
            available_loras = self.filter_set.apply(available_loras, criteria)

        # Apply license filters
        # no_credit_required=True means keep only models where credit is NOT required
        # (i.e., allowNoCredit=True, which is bit 0 = 1 in license_flags)
        if no_credit_required:
            available_loras = [
                lora
                for lora in available_loras
                if bool(lora.get("license_flags", 127) & (1 << 0))
            ]

        # allow_selling=True means keep only models where selling generated content is allowed
        if allow_selling:
            available_loras = [
                lora
                for lora in available_loras
                if bool(lora.get("license_flags", 127) & (1 << 1))
            ]

        return available_loras
