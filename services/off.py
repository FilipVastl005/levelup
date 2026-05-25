import httpx
import logging

logger = logging.getLogger(__name__)

async def get_off_product(ean: str):
    """
    Fetch product data from Open Food Facts API.
    """
    url = f"https://world.openfoodfacts.org/api/v2/product/{ean}.json"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("status") == 1:
                    product = data["product"]
                    # Extract useful fields
                    return {
                        "ean": ean,
                        "name": product.get("product_name", "Unknown"),
                        "brand": product.get("brands", ""),
                        "ingredients": product.get("ingredients_text", ""),
                        "allergens": product.get("allergens", ""),
                        "nutrition": product.get("nutriments", {}),
                        "nutrition_score": product.get("nutriscore_grade", ""),
                        "source": "OFF"
                    }
            return None
    except Exception as e:
        logger.error(f"Error fetching from OFF: {e}")
        return None
