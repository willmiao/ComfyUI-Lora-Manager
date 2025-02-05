import aiohttp
from .base import MetadataProvider

class CivitaiProvider(MetadataProvider):
    """CivitAI metadata provider implementation"""
    
    def __init__(self):
        self.base_url = "https://civitai.com/api/v1"
        self.session = aiohttp.ClientSession()
    
    @property
    def name(self) -> str:
        return "civitai"
        
    async def get_model_by_hash(self, model_hash: str) -> Optional[Dict]:
        try:
            async with self.session.get(f"{self.base_url}/model-versions/by-hash/{model_hash}") as response:
                if response.status == 200:
                    return await response.json()
                return None
        except Exception as e:
            print(f"API Error: {str(e)}")
            return None
        
    async def download_preview(self, image_url: str, save_path: str) -> bool:
        try:
            async with self.session.get(image_url) as response:
                if response.status == 200:
                    content = await response.read()
                    with open(save_path, 'wb') as f:
                        f.write(content)
                    return True
                return False
        except Exception as e:
            print(f"Download Error: {str(e)}")
            return False
        
    def format_metadata(self, data: Dict) -> Dict:
        # Standardize field mapping
        return {
            "id": data.get("id"),
            "model_id": data.get("modelId"), 
            "name": data.get("name"),
            "description": data.get("description"),
            "base_model": data.get("baseModel"),
            "trigger_words": data.get("trainedWords", []),
            "previews": [
                {
                    "url": img["url"],
                    "type": img.get("type", "image")
                }
                for img in data.get("images", [])
            ]
        }
        
    async def close(self):
        await self.session.close()
