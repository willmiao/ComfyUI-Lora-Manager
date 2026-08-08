from dataclasses import dataclass, asdict, field
from typing import Dict, Optional, List, Any
from datetime import datetime
import os
from .constants import INVALID_AUTOV3_EMPTY_HASH
from .model_utils import determine_base_model


def normalize_autov3(value: Any) -> Optional[str]:
    """Normalize a raw Civitai AutoV3 value to the canonical 12-char form.

    Returns the first 12 characters, lowercased, when ``value`` is a string
    of at least 12 characters. The empty-string SHA256 placeholder
    (``e3b0c44298fc``) is rejected — it is a repackaging-tool artifact, not a
    real hash.

    Returns ``None`` when the value is unusable.
    """
    if isinstance(value, str) and len(value) >= 12:
        candidate = value[:12].lower()
        if candidate != INVALID_AUTOV3_EMPTY_HASH:
            return candidate
    return None


def autov3_from_civitai_files(civitai_data: Optional[Dict], sha256: str) -> Optional[str]:
    """Extract the AutoV3 hash from Civitai metadata for the matching file.

    Civitai versions can ship multiple files; the AutoV3 hash is only valid
    for the file whose ``hashes.SHA256`` equals the local model's sha256.
    Matching is case-insensitive.

    Returns ``None`` when no Civitai data, no matching file, or no usable
    AutoV3 hash is available.
    """
    if not civitai_data or not sha256:
        return None
    target_sha = sha256.lower()
    for file_info in civitai_data.get("files") or []:
        if not isinstance(file_info, dict):
            continue
        hashes = file_info.get("hashes") or {}
        file_sha = (hashes.get("SHA256") or "").lower()
        if file_sha and file_sha == target_sha:
            return normalize_autov3(hashes.get("AutoV3"))
    return None


@dataclass
class BaseModelMetadata:
    """Base class for all model metadata structures"""

    file_name: str  # The filename without extension
    model_name: str  # The model's name defined by the creator
    file_path: str  # Full path to the model file
    size: int  # File size in bytes
    modified: float  # Timestamp when the model was added to the management system
    sha256: str  # SHA256 hash of the file
    base_model: str  # Base model type (SD1.5/SD2.1/SDXL/etc.)
    preview_url: str  # Preview image URL
    preview_nsfw_level: int = 0  # NSFW level of the preview image
    notes: str = ""  # Additional notes
    from_civitai: bool = True  # Whether from Civitai
    civitai: Dict[str, Any] = field(
        default_factory=dict
    )  # Civitai API data if available
    tags: List[str] = None  # Model tags
    modelDescription: str = ""  # Full model description
    civitai_deleted: bool = False  # Whether deleted from Civitai
    favorite: bool = False  # Whether the model is a favorite
    exclude: bool = False  # Whether to exclude this model from the cache
    db_checked: bool = False  # Whether checked in archive DB
    skip_metadata_refresh: bool = (
        False  # Whether to skip this model during bulk metadata refresh
    )
    metadata_source: Optional[str] = None  # Last provider that supplied metadata
    last_checked_at: float = 0  # Last checked timestamp
    hash_status: str = "completed"  # Hash calculation status: pending | calculating | completed | failed
    autov3: Optional[str] = None  # CivitAI AutoV3 hash (12-char lowercase hex); "" = checked but unavailable, None = not checked
    trainedWords: List[str] = field(
        default_factory=list
    )  # Trigger words / activation prompts (source-agnostic)
    _unknown_fields: Dict[str, Any] = field(
        default_factory=dict, repr=False, compare=False
    )  # Store unknown fields

    def __post_init__(self):
        # Initialize empty lists to avoid mutable default parameter issue
        if self.civitai is None:
            self.civitai = {}

        if self.tags is None:
            self.tags = []

        if self.trainedWords is None:
            self.trainedWords = []

    @classmethod
    def from_dict(cls, data: Dict) -> "BaseModelMetadata":
        """Create instance from dictionary"""
        data_copy = data.copy()

        # autov3 three-state semantics: an explicit key means the value is known.
        # JSON null in the sidecar ("checked but unavailable") is normalized to ""
        # in memory; an absent key stays None ("not checked yet"). autov3 is a known
        # field, so it flows through fields_to_use below and never leaks into
        # _unknown_fields.
        if "autov3" in data_copy:
            data_copy["autov3"] = data_copy["autov3"] or ""

        # Use cached fields if available, otherwise compute them
        if not hasattr(cls, "_known_fields_cache"):
            known_fields = set()
            for c in cls.mro():
                if hasattr(c, "__annotations__"):
                    known_fields.update(c.__annotations__.keys())
            cls._known_fields_cache = known_fields

        known_fields = cls._known_fields_cache

        # Extract fields that match our class attributes
        fields_to_use = {k: v for k, v in data_copy.items() if k in known_fields}

        # Store unknown fields separately
        unknown_fields = {
            k: v
            for k, v in data_copy.items()
            if k not in known_fields and not k.startswith("_")
        }

        # Create instance with known fields
        instance = cls(**fields_to_use)

        # Add unknown fields as a separate attribute
        instance._unknown_fields = unknown_fields

        return instance

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization"""
        result = asdict(self)

        # Remove private fields
        result = {k: v for k, v in result.items() if not k.startswith("_")}

        # Add back unknown fields if they exist
        if hasattr(self, "_unknown_fields"):
            result.update(self._unknown_fields)

        # autov3 three-state semantics: emit the key only when the value is known.
        # "" is serialized as JSON null ("checked but unavailable"); an absent key
        # means "not checked yet". Done after unknown fields so a stale unknown
        # copy can never override the typed field.
        if self.autov3 is not None:
            result["autov3"] = self.autov3 or None
        else:
            result.pop("autov3", None)

        return result

    def update_civitai_info(self, civitai_data: Dict) -> None:
        """Update Civitai information.

        Civitai's AutoV3 is the authoritative hash for recipe matching, so
        whenever the version metadata reports an AutoV3 for the file whose
        SHA256 matches this model, it takes precedence over the locally
        extracted header hash.
        """
        self.civitai = civitai_data
        autov3 = autov3_from_civitai_files(civitai_data, self.sha256)
        if autov3:
            self.autov3 = autov3

    def update_file_info(self, file_path: str, update_timestamps: bool = False) -> None:
        """
        Update metadata with actual file information.

        Args:
            file_path: Path to the model file
            update_timestamps: If True, update size and modified from filesystem.
                              If False (default), only update file_path and file_name.
                              Set to True only when file has been moved/relocated.
        """
        if os.path.exists(file_path):
            if update_timestamps:
                # Only update size and modified when file has been relocated
                self.size = os.path.getsize(file_path)
                self.modified = os.path.getmtime(file_path)
            # Always update paths when this method is called
            self.file_path = file_path.replace(os.sep, "/")
            self.file_name = os.path.splitext(os.path.basename(file_path))[0]

    @staticmethod
    def generate_unique_filename(
        target_dir: str, base_name: str, extension: str, hash_provider: callable = None
    ) -> str:
        """Generate a unique filename to avoid conflicts

        Args:
            target_dir: Target directory path
            base_name: Base filename without extension
            extension: File extension including the dot
            hash_provider: A callable that returns the SHA256 hash when needed

        Returns:
            str: Unique filename that doesn't conflict with existing files
        """
        original_filename = f"{base_name}{extension}"
        target_path = os.path.join(target_dir, original_filename)

        # If no conflict, return original filename
        if not os.path.exists(target_path):
            return original_filename

        # Only compute hash when needed
        if hash_provider:
            sha256_hash = hash_provider()
        else:
            sha256_hash = "0000"

        # Generate short hash (first 4 characters of SHA256)
        short_hash = sha256_hash[:4] if sha256_hash else "0000"

        # Try with short hash suffix
        unique_filename = f"{base_name}-{short_hash}{extension}"
        unique_path = os.path.join(target_dir, unique_filename)

        # If still conflicts, add incremental number
        counter = 1
        while os.path.exists(unique_path):
            unique_filename = f"{base_name}-{short_hash}-{counter}{extension}"
            unique_path = os.path.join(target_dir, unique_filename)
            counter += 1

        return unique_filename


@dataclass
class LoraMetadata(BaseModelMetadata):
    """Represents the metadata structure for a Lora model"""

    usage_tips: str = "{}"  # Usage tips for the model, json string

    @classmethod
    def from_civitai_info(
        cls, version_info: Dict, file_info: Dict, save_path: str
    ) -> "LoraMetadata":
        """Create LoraMetadata instance from Civitai version info"""
        file_name = file_info.get("name", "")
        base_model = determine_base_model(version_info.get("baseModel", ""))

        # Extract tags and description if available
        tags = []
        description = ""
        model_data = version_info.get("model") or {}
        if "tags" in model_data:
            tags = model_data["tags"]
        if "description" in model_data:
            description = model_data["description"]

        sha256_value = (file_info.get("hashes") or {}).get("SHA256", "").lower()

        return cls(
            file_name=os.path.splitext(file_name)[0],
            model_name=model_data.get("name", os.path.splitext(file_name)[0]),
            file_path=save_path.replace(os.sep, "/"),
            size=file_info.get("sizeKB", 0) * 1024,
            modified=datetime.now().timestamp(),
            sha256=sha256_value,
            base_model=base_model,
            preview_url="",  # Will be updated after preview download
            preview_nsfw_level=0,  # Will be updated after preview download
            from_civitai=True,
            civitai=version_info,
            tags=tags,
            modelDescription=description,
            # Direct read: the downloaded file IS file_info, no SHA256 matching.
            autov3=normalize_autov3((file_info.get("hashes") or {}).get("AutoV3")),
        )


@dataclass
class CheckpointMetadata(BaseModelMetadata):
    """Represents the metadata structure for a Checkpoint model"""

    sub_type: str = "checkpoint"  # Model sub-type (checkpoint, diffusion_model, etc.)

    @classmethod
    def from_civitai_info(
        cls, version_info: Dict, file_info: Dict, save_path: str
    ) -> "CheckpointMetadata":
        """Create CheckpointMetadata instance from Civitai version info"""
        file_name = file_info.get("name", "")
        base_model = determine_base_model(version_info.get("baseModel", ""))
        sha256_value = (file_info.get("hashes") or {}).get("SHA256", "").lower()
        sub_type = version_info.get("type", "checkpoint")

        # Extract tags and description if available
        tags = []
        description = ""
        model_data = version_info.get("model") or {}
        if "tags" in model_data:
            tags = model_data["tags"]
        if "description" in model_data:
            description = model_data["description"]

        return cls(
            file_name=os.path.splitext(file_name)[0],
            model_name=model_data.get("name", os.path.splitext(file_name)[0]),
            file_path=save_path.replace(os.sep, "/"),
            size=file_info.get("sizeKB", 0) * 1024,
            modified=datetime.now().timestamp(),
            sha256=sha256_value,
            base_model=base_model,
            preview_url="",  # Will be updated after preview download
            preview_nsfw_level=0,
            from_civitai=True,
            civitai=version_info,
            sub_type=sub_type,
            tags=tags,
            modelDescription=description,
            # Direct read: the downloaded file IS file_info, no SHA256 matching.
            autov3=normalize_autov3((file_info.get("hashes") or {}).get("AutoV3")),
        )


@dataclass
class EmbeddingMetadata(BaseModelMetadata):
    """Represents the metadata structure for an Embedding model"""

    sub_type: str = "embedding"

    @classmethod
    def from_civitai_info(
        cls, version_info: Dict, file_info: Dict, save_path: str
    ) -> "EmbeddingMetadata":
        """Create EmbeddingMetadata instance from Civitai version info"""
        file_name = file_info.get("name", "")
        base_model = determine_base_model(version_info.get("baseModel", ""))
        sha256_value = (file_info.get("hashes") or {}).get("SHA256", "").lower()
        sub_type = version_info.get("type", "embedding")

        # Extract tags and description if available
        tags = []
        description = ""
        model_data = version_info.get("model") or {}
        if "tags" in model_data:
            tags = model_data["tags"]
        if "description" in model_data:
            description = model_data["description"]

        return cls(
            file_name=os.path.splitext(file_name)[0],
            model_name=model_data.get("name", os.path.splitext(file_name)[0]),
            file_path=save_path.replace(os.sep, "/"),
            size=file_info.get("sizeKB", 0) * 1024,
            modified=datetime.now().timestamp(),
            sha256=sha256_value,
            base_model=base_model,
            preview_url="",  # Will be updated after preview download
            preview_nsfw_level=0,
            from_civitai=True,
            civitai=version_info,
            sub_type=sub_type,
            tags=tags,
            modelDescription=description,
            # Direct read: the downloaded file IS file_info, no SHA256 matching.
            autov3=normalize_autov3((file_info.get("hashes") or {}).get("AutoV3")),
        )
