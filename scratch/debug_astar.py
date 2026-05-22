import asyncio
from httpx import AsyncClient

async def main():
    async with AsyncClient() as client:
        # Load the benchmark
        resp = await client.post("http://127.0.0.1:8000/api/schedule-benchmark/a_star/ENSIA_S1")
        # We need to stream the response
        buffer = b""
        async for chunk in resp.aiter_bytes():
            buffer += chunk
        
        text = buffer.decode()
        for line in text.split('\n'):
            if line.startswith('data: '):
                print(line[:150] + '...')

if __name__ == "__main__":
    asyncio.run(main())
