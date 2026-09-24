from fastapi import FastAPI
from document_validator.router import router as document_validator_router

app = FastAPI()

app.include_router(document_validator_router)

@app.get("/")
def read_root():
    return {"message": "MahaClear-AI backend is running"}