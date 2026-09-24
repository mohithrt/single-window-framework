from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from document_validator.router import router as document_validator_router

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(document_validator_router)

@app.get("/")
def read_root():
    return {"message": "MahaClear-AI backend is running"}