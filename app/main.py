from fastapi import FastAPI

app = FastAPI(title="AI Codebase Assistant")

@app.get("/")
def root():
    return {"status": "ok"}