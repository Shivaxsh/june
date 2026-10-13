"""Read June's actual local backend status without starting model generation."""
import asyncio
import httpx


async def main():
    async with httpx.AsyncClient(trust_env=False) as client:
        response = await client.get('http://127.0.0.1:8001/api/status', timeout=5)
        response.raise_for_status()
        print(response.json())


if __name__ == '__main__':
    asyncio.run(main())
