from fastapi import APIRouter, HTTPException, Query, Form, Depends, UploadFile, File
from typing import Optional
from datetime import datetime
from .model import WeatherResponse, WeatherSimpleResponse, HealthResponse, Entrada
import asyncio
import aiohttp
from sqlalchemy.orm import Session
from backend.database import conectar_db
import base64

router = APIRouter()

# Conexion al API
class WeatherAPI:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.openweathermap.org/data/2.5"
    
    async def get_weather(self, ciudad: str, units: str = "metric"):
        url = f"{self.base_url}/weather"
        params = {'q': ciudad, 'appid': self.api_key, 'units': units, 'lang': 'es'}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=10) as response:
                    if response.status == 200:
                        return await response.json()
                    raise HTTPException(status_code=response.status, detail=f"Error: {response.status}")
        except asyncio.TimeoutError:
            raise HTTPException(status_code=408, detail="Timeout en la solicitud")
        except aiohttp.ClientError as e:
            raise HTTPException(status_code=500, detail=f"Error de conexión: {str(e)}")

    async def get_weather_formatted(self, ciudad: str, units: str = "metric") -> WeatherResponse:
        datos = await self.get_weather(ciudad, units)
        try:
            return WeatherResponse(
                ciudad=datos['name'],
                pais=datos['sys']['country'],
                temperatura=datos['main']['temp'],
                sensacion_termica=datos['main']['feels_like'],
                temp_min=datos['main']['temp_min'],
                temp_max=datos['main']['temp_max'],
                humedad=datos['main']['humidity'],
                presion=datos['main']['pressure'],
                descripcion=datos['weather'][0]['description'],
                icono=datos['weather'][0]['icon'],
                nubosidad=datos['clouds']['all'],
                viento_velocidad=datos.get('wind', {}).get('speed', 0),
                viento_direccion=datos.get('wind', {}).get('deg', 0),
                visibilidad=datos.get('visibility', 0),
                amanecer=datetime.fromtimestamp(datos['sys']['sunrise']).strftime('%H:%M:%S'),
                atardecer=datetime.fromtimestamp(datos['sys']['sunset']).strftime('%H:%M:%S'),
                coordenadas={'latitud': datos['coord']['lat'], 'longitud': datos['coord']['lon']},
                timestamp=datetime.now().isoformat()
            )
        except KeyError as e:
            raise HTTPException(status_code=500, detail=f"Error de estructura: {str(e)}")

# Instancia con tu API key
weather_api = WeatherAPI(api_key="a54fc02404ab14f7755566fe1a2cafd8")

@router.get("/")
async def root():
    return {
        "message": "API del Clima",
        "version": "1.0.0",
        "docs": "/docs",
        "endpoints": ["/weather/{ciudad}", "/health"]
    }

@router.get("/weather_api/{ciudad}")
async def get_weather(ciudad: str, format: Optional[str] = "complete", units: Optional[str] = "metric"):
    if units not in ['metric', 'imperial', 'kelvin']:
        raise HTTPException(status_code=400, detail="Unidades inválidas")

    if format == "simple":
        data = await weather_api.get_weather(ciudad, units)
        return WeatherSimpleResponse(
            ciudad=data['name'],
            temperatura=data['main']['temp'],
            descripcion=data['weather'][0]['description'],
            humedad=data['main']['humidity'],
            unidades=units
        )
    return await weather_api.get_weather_formatted(ciudad, units)

@router.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(
        status="OK",
        timestamp=datetime.now().isoformat(),
        message="API funcionando correctamente"
    )

@router.post("/weather")
def guardar_clima(entry: WeatherResponse):
    try:
        conn = conectar_db()
        with conn.cursor() as cursor:
            sql = """
                INSERT INTO weather_data (
                    ciudad, pais, temperatura, sensacion_termica, temp_min, temp_max,
                    humedad, presion, descripcion, icono, nubosidad,
                    viento_velocidad, viento_direccion, visibilidad,
                    amanecer, atardecer, latitud, longitud, timestamp
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            cursor.execute(sql, (
                entry.ciudad,
                entry.pais,
                entry.temperatura,
                entry.sensacion_termica,
                entry.temp_min,
                entry.temp_max,
                entry.humedad,
                entry.presion,
                entry.descripcion,
                entry.icono,
                entry.nubosidad,
                entry.viento_velocidad,
                entry.viento_direccion,
                entry.visibilidad,
                entry.amanecer,
                entry.atardecer,
                entry.coordenadas["latitud"],
                entry.coordenadas["longitud"],
                entry.timestamp
            ))
            conn.commit()
        return {"message": "Clima guardado correctamente"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@router.get("/weather")
def listar_climas():
    try:
        conn = conectar_db()
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM weather_data")
            rows = cursor.fetchall()
        return rows
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@router.post("/entradas")
async def crear_entrada(
    nombre: str = Form(...),
    ciudad: str = Form(...),
    clima: str = Form(...),
    descripcion: str = Form(None),
    imagen: UploadFile = File(None)
):
    imagen_str = None

    try:
        if imagen:
            contenido = await imagen.read()
            imagen_str = base64.b64encode(contenido).decode("utf-8")

        conn = conectar_db()
        with conn.cursor() as cursor:
            sql = """
                INSERT INTO entradas (nombre, ciudad, clima, descripcion, imagen)
                VALUES (%s, %s, %s, %s, %s)
            """
            cursor.execute(sql, (
                nombre,
                ciudad,
                clima,
                descripcion,
                imagen_str
            ))
            conn.commit()
            new_id = cursor.lastrowid  # ✅ Aquí obtienes el ID generado automáticamente

        return {
            "message": "Entrada creada exitosamente",
            "entrada": {
                "id": new_id
            }
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()



@router.get("/entradas")
def listar_entradas():
    try:
        conn = conectar_db()
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM entradas")
            rows = cursor.fetchall()  # Ya es una lista de diccionarios
        return rows
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


