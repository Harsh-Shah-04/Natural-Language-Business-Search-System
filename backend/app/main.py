from fastapi import FastAPI

app = FastAPI(title="Business Search Backend")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
