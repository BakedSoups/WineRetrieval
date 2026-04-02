import os

from dotenv import load_dotenv

load_dotenv()

WARMUP_MODEL = os.getenv("SIE_WARMUP_MODEL", "NovaSearch/stella_en_400M_v5")
WARMUP_GPU = os.getenv("SIE_WARMUP_GPU", "l4-spot")
WARMUP_TIMEOUT_S = int(os.getenv("SIE_WARMUP_TIMEOUT_S", "900"))


def main():
    cluster_url = os.getenv("CLUSTER_URL")
    api_key = os.getenv("API_KEY")

    if not cluster_url:
        raise ValueError("Missing CLUSTER_URL in the environment.")
    if not api_key:
        raise ValueError("Missing API_KEY in the environment.")

    try:
        from sie_sdk import SIEClient
        from sie_sdk.types import Item
        from sie_sdk.client.errors import SIEConnectionError
    except ImportError as exc:
        raise ImportError("sie_sdk is required to warm up the remote SIE endpoint.") from exc

    print(f"Warming up SIE at {cluster_url}...", flush=True)
    print(f"Model: {WARMUP_MODEL}", flush=True)
    print(f"GPU: {WARMUP_GPU}", flush=True)
    client = SIEClient(cluster_url, api_key=api_key)
    try:
        result = client.encode(
            WARMUP_MODEL,
            Item(text="warmup"),
            gpu=WARMUP_GPU,
            wait_for_capacity=True,
            provision_timeout_s=WARMUP_TIMEOUT_S,
        )
    except SIEConnectionError as exc:
        print("SIE warmup failed: remote connection error.", flush=True)
        print(f"Configured CLUSTER_URL: {cluster_url}", flush=True)
        print(f"Error: {exc}", flush=True)
        raise

    dense_vector = result.get("dense")
    if dense_vector is None:
        dense_vector = []
    print("SIE warmup completed.", flush=True)
    print(f"Dense vector length: {len(dense_vector)}")


if __name__ == "__main__":
    main()
