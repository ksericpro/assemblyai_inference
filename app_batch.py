# Start by making sure the `assemblyai` package is installed.
# If not, you can install it by running the following command:
# pip install -U assemblyai
#
# Note: Some macOS users may need to use `pip3` instead of `pip`.

import assemblyai as aai
from dotenv import load_dotenv
import os, signal
from random import randrange

from fastapi import FastAPI, WebSocket, Request
from starlette.responses import HTMLResponse
from starlette.websockets import WebSocket, WebSocketDisconnect
from fastapi.templating import Jinja2Templates

import uvicorn
import threading, time
import base64
import asyncio
from typing import List

import msgsplitter

load_dotenv()  # take environment variables from .env.
# Replace with your API key
aai.settings.api_key = os.environ['ASSEMBLY_AI_APIKEY']
FILE_URL = os.environ['FILE_URL']

# api
app = FastAPI()
PORT = 8001

class Notifier:
    def __init__(self):
        self.connections: List[WebSocket] = []
        self.generator = self.get_notification_generator()

    async def get_notification_generator(self):
        while True:
            message = yield
            await self._notify(message)

    async def push(self, msg: str):
        await self.generator.asend(msg)

    async def pushBytes(self, buffer):
        living_connections = []
        while len(self.connections) > 0:
            # Looping like this is necessary in case a disconnection is handled
            websocket = self.connections.pop()
            await websocket.send_bytes(buffer)
            living_connections.append(websocket)
        self.connections = living_connections

    async def connect(self, websocket: WebSocket):
        print("New Client Connected")
        await websocket.accept()
        self.connections.append(websocket)

    def remove(self, websocket: WebSocket):
        print("Client Disconnected")
        self.connections.remove(websocket)

    async def _notify(self, message: str):
        living_connections = []
        while len(self.connections) > 0:
            # Looping like this is necessary in case a disconnection is handled
            # during await websocket.send_text(message)
            websocket = self.connections.pop()
            await websocket.send_text(message)
            living_connections.append(websocket)
        self.connections = living_connections


notifier = Notifier()

#WB = []

templates = Jinja2Templates(directory="templates")

@app.get('/')
def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await notifier.connect(websocket)
   # print("New Socket")
   # WB.append(websocket)
    try:
       while True:
            data = await websocket.receive_text()
            await websocket.send_text(f"Message text was: {data}")
    except WebSocketDisconnect:
        notifier.remove(websocket)

@app.on_event("startup")
async def startup():
    # Prime the push notification generator
    await notifier.generator.asend(None)

    _streaming_thread = threading.Thread(target=asyncio.run, args=(start_streaming(notifier),))
    _streaming_thread.start()


# URL of the file to transcribe
#FILE_URL = "https://github.com/AssemblyAI-Examples/audio-examples/raw/main/20230607_me_canadian_wildfires.mp3"

# You can also transcribe a local file by passing in a file path
# FILE_URL = './path/to/file.mp3'
def handler(signum, frame):
    print("Ctrl-c was pressed")
    exit(1)

async def start_streaming(_notifier):
    print("Starting Audio Streaming...")
    start = time.time()

    print("Reading & Transcribing {}".format(FILE_URL))
    transcriber = aai.Transcriber()
    transcript = transcriber.transcribe(FILE_URL)

    if transcript.status == aai.TranscriptStatus.error:
        print(transcript.error)
    else:
        print(transcript.text)
        await start_broadcast_msg(_notifier, transcript.text)

    end = time.time()
    print('Execution Time: {}'.format(end-start))

async def start_broadcast_msg(_notifier, message):
    print("Starting broadcast_msg...")
    list = msgsplitter.split(message, length_limit=150,)
    ct = len(list)
    while True:
        for x in range(ct):
            await _notifier.push(list[x])
            time.sleep(randrange(5))

if __name__=="__main__":
    signal.signal(signal.SIGINT, handler)
    uvicorn.run("app_batch:app",host='0.0.0.0', port=PORT, reload=True, workers=3)