from fastapi import FastAPI

from app.routers import admin, ai, appointments, auth, catalog

app = FastAPI(title="Salon AI")
app.include_router(auth.router)
app.include_router(catalog.router)
app.include_router(appointments.router)
app.include_router(admin.router)
app.include_router(ai.router)
