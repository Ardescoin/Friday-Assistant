from fastapi import FastAPI, HTTPException, Request, UploadFile, File
from pydantic import BaseModel
import uuid
import time
import sqlite3
import os
import edge_tts
from fastapi.responses import FileResponse
import asyncio
import requests

app = FastAPI()

DB_PATH = "/root/my_server/db/neural_network_memory.db"
FILES_DIR = "/root/my_server/files"  

def init_db():
    if not os.path.exists(DB_PATH):
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS interactions
                     (timestamp REAL, command TEXT, response TEXT)''')
        conn.commit()
        conn.close()
    os.makedirs(FILES_DIR, exist_ok=True)

init_db()

pc_status = {"active": False}
command_queue = {}
file_queue = [] 

class CommandRequest(BaseModel):
    command: str

class ResponseRequest(BaseModel):
    command_id: str
    response: str

class InteractionRequest(BaseModel):
    command: str
    prompt: str
    response: str

class TTSRequest(BaseModel):
    text: str

class FileSendRequest(BaseModel):
    filename: str

@app.post("/pc/status")
async def update_pc_status(status: dict):
    was_active = pc_status["active"]
    pc_status["active"] = status.get("active", False)
    return {"status": "PC status updated", "active": pc_status["active"]}

@app.get("/pc/status")
async def get_pc_status():
    return {"active": pc_status["active"]}

@app.post("/pc/command")
async def send_pc_command(request: CommandRequest, fastapi_request: Request):
    client_ip = fastapi_request.client.host
    if pc_status["active"]:
        if request.command == "check":
            if command_queue:
                for command_id, cmd_data in list(command_queue.items()):
                    if cmd_data["response"] is None:
                        return {"command_id": command_id, "command": cmd_data["command"], "status": "sent"}
            return {"status": "no_command"}
        else:
            command_id = str(uuid.uuid4())
            command_queue[command_id] = {"command": request.command, "response": None, "timestamp": time.time()}
            return {"command_id": command_id, "status": "sent"}
    else:
        raise HTTPException(status_code=503, detail="ПК не активен")

@app.post("/pc/response")
async def receive_pc_response(request: ResponseRequest):
    if request.command_id in command_queue:
        command_queue[request.command_id]["response"] = request.response
        return {"status": "Response received"}
    raise HTTPException(status_code=404, detail="Command ID not found")

@app.get("/pc/response/{command_id}")
async def get_pc_response(command_id: str):
    if command_id in command_queue and command_queue[command_id]["response"] is not None:
        return {"response": command_queue[command_id]["response"]}
    raise HTTPException(status_code=404, detail="Response not ready or not found")

@app.get("/db/get_interactions")
async def get_interactions():
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT timestamp, command, response FROM interactions ORDER BY timestamp ASC")
        rows = c.fetchall()
        if rows:
            context_lines = [f"Пользователь: {row[1]}\nПятница: {row[2]}" for row in rows]
            context = "\n".join(context_lines)
        else:
            context = "Контекст пока пуст"
        conn.close()
        return {"context": context}
    except sqlite3.Error as e:
        raise HTTPException(status_code=500, detail=f"Ошибка базы данных: {str(e)}")

@app.post("/db/add_interaction")
async def add_interaction(request: InteractionRequest):
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("INSERT INTO interactions (timestamp, command, response) VALUES (?, ?, ?)",
                  (time.time(), request.command, request.response))
        conn.commit()
        conn.close()
        return {"status": "Interaction added"}
    except sqlite3.Error as e:
        raise HTTPException(status_code=500, detail=f"Ошибка базы данных: {str(e)}")

@app.post("/tts")
async def text_to_speech(request: TTSRequest):
    try:
        communicate = edge_tts.Communicate(request.text, "ru-RU-SvetlanaNeural")
        audio_file = f"output.mp3"
        await communicate.save(audio_file)
        return FileResponse(audio_file, media_type="audio/mpeg", filename="response.mp3")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка генерации речи: {str(e)}")


@app.post("/pc/receive_file")
async def receive_file_to_pc(file: UploadFile = File(...)):
    filename = file.filename
    temp_path = os.path.join(FILES_DIR, filename)
    try:
        
        with open(temp_path, "wb") as f:
            f.write(await file.read())
        file_queue.append({"filename": filename})  
        if pc_status["active"]:
            return {"status": "Файл сохранён на сервере и готов к передаче на ПК", "filename": filename}
        else:
            return {"status": "Файл сохранён на сервере и ждёт активации ПК", "filename": filename}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка при сохранении файла: {str(e)}")


@app.post("/pc/send_file")
async def send_file_from_pc(request: FileSendRequest):
    if not pc_status["active"]:
        raise HTTPException(status_code=503, detail="ПК не активен")
    temp_path = os.path.join(FILES_DIR, request.filename)
    if not os.path.exists(temp_path):
        raise HTTPException(status_code=404, detail=f"Файл {request.filename} не найден на сервере")
    return FileResponse(temp_path, media_type="application/octet-stream", filename=request.filename)


@app.get("/pc/get_file/{filename}")
async def get_file(filename: str):
    if not pc_status["active"]:
        raise HTTPException(status_code=503, detail="ПК не активен")
    file_path = os.path.join(FILES_DIR, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"Файл {filename} не найден на сервере")
    return FileResponse(file_path, media_type="application/octet-stream", filename=filename)


@app.get("/pc/check_file_queue")
async def check_file_queue():
    if not pc_status["active"]:
        return {"files": [], "status": "ПК не активен"}
    files_to_send = [{"filename": file_data["filename"]} for file_data in file_queue]
    return {"files": files_to_send, "status": "Files available"}

@app.delete("/pc/remove_file/{filename}")
async def remove_file(filename: str):
    file_path = os.path.join(FILES_DIR, filename)
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            file_queue[:] = [f for f in file_queue if f["filename"] != filename]
            return {"status": f"Файл {filename} удалён с сервера"}
        else:
            raise HTTPException(status_code=404, detail=f"Файл {filename} не найден на сервере")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка удаления файла: {str(e)}")