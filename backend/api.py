# api.py

from fastapi import FastAPI, HTTPException, UploadFile, File
from langserve import add_routes
from summarizeurl import summarize_url_runnable
from chaturl import create_chain
from summarize_youtube import summarize_youtube_video
from chat_youtube import chat_with_youtube
from transcript_processing import summarize_meeting_transcript
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, HttpUrl
from typing import Optional
import logging
import requests

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
  title="URL and YouTube Summarizer and Chat API",
  version="1.1",
  description="An API for summarizing web pages and YouTube videos, and chatting about their content.",
)

app.add_middleware(
  CORSMiddleware,
  allow_origins=["http://localhost:3000"],  # Replace with your frontend URL
  allow_credentials=True,
  allow_methods=["*"],
  allow_headers=["*"],
)

class TranscriptSummarizeRequest(BaseModel):
    file: UploadFile

class TranscriptChatRequest(BaseModel):
    file: Optional[UploadFile] = None
    question: str
    session_id: str

class URLSummarizeRequest(BaseModel):
  url: HttpUrl

class URLChatRequest(BaseModel):
  url: HttpUrl
  question: str
  session_id: str

class YouTubeSummarizeRequest(BaseModel):
  url: HttpUrl

class YouTubeChatRequest(BaseModel):
  url: HttpUrl
  question: str
  session_id: str

@app.post("/summarize-transcript")
async def summarize_transcript(file: UploadFile = File(...)):
    try:
        summary = await summarize_meeting_transcript(file)
        return {"output": summary}
    except Exception as e:
        logger.error(f"Error in /summarize-transcript endpoint: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/chat-transcript")
async def chat_transcript(request: TranscriptChatRequest):
    try:
        response = await chat_with_meeting_transcript(request.file, request.question, request.session_id)
        return {"output": response}
    except Exception as e:
        logger.error(f"Error in /chat-transcript endpoint: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/summarize")
async def summarize(request: URLSummarizeRequest):
  try:
      # First, check if the URL is accessible
      response = requests.head(str(request.url))
      response.raise_for_status()

      summary = await summarize_url_runnable.ainvoke(request.url)
      return {"output": summary}
  except requests.exceptions.HTTPError as e:
      logger.error(f"HTTP Error in /summarize endpoint: {e}")
      if e.response.status_code == 403:
          error_message = "Access to this website is forbidden. The website may be blocking automated access or scraping."
      elif e.response.status_code == 404:
          error_message = "The requested URL was not found. Please check if the URL is correct."
      else:
          error_message = f"An HTTP error occurred: {e}. The website may be inaccessible or blocking requests."
      raise HTTPException(status_code=400, detail=error_message)
  except requests.exceptions.ConnectionError:
      logger.error("Connection Error in /summarize endpoint")
      error_message = "Unable to connect to the website. The site may be down or blocking requests."
      raise HTTPException(status_code=400, detail=error_message)
  except requests.exceptions.Timeout:
      logger.error("Timeout Error in /summarize endpoint")
      error_message = "The request to the website timed out. The site may be slow or unresponsive."
      raise HTTPException(status_code=400, detail=error_message)
  except requests.exceptions.RequestException as e:
      logger.error(f"Request Exception in /summarize endpoint: {e}")
      error_message = "An error occurred while trying to access the website. It may be inaccessible or blocking requests."
      raise HTTPException(status_code=400, detail=error_message)
  except Exception as e:
      logger.error(f"Unexpected error in /summarize endpoint: {e}")
      error_message = "An unexpected error occurred while summarizing the web page. Please try a different URL."
      raise HTTPException(status_code=500, detail=error_message)

@app.post("/chat")
async def chat(input: URLChatRequest):
  url = input.url
  question = input.question
  session_id = input.session_id

  if not url or not question:
      raise HTTPException(status_code=400, detail="Both URL and question are required")
  
  try:
      chain = create_chain(url)
      response = await chain.ainvoke({"input": question}, config={"configurable": {"session_id": session_id}})
      return {"output": response["answer"]}
  except ValueError as e:
      logger.error(f"Error in /chat endpoint: {e}")
      error_message = f"An error occurred while processing your request: {str(e)}. The URL may be inaccessible or not suitable for chat."
      raise HTTPException(status_code=400, detail=error_message)
  except Exception as e:
      logger.error(f"Unexpected error in /chat endpoint: {e}")
      error_message = "An unexpected error occurred while processing your request. Please try a different URL or question."
      raise HTTPException(status_code=500, detail=error_message)

@app.post("/summarize-youtube")
async def summarize_youtube(request: YouTubeSummarizeRequest):
  try:
      logger.info(f"Received request to summarize YouTube video: {request.url}")
      summary = await summarize_youtube_video(str(request.url))
      logger.info("Successfully generated summary for YouTube video")
      return {"output": summary}
  except Exception as e:
      logger.error(f"Error in /summarize-youtube endpoint: {e}")
      error_message = f"An error occurred while summarizing the YouTube video: {str(e)}. Please check the URL and try again."
      raise HTTPException(status_code=400, detail=error_message)

@app.post("/chat-youtube")
async def chat_youtube(input: YouTubeChatRequest):
  url = input.url
  question = input.question
  session_id = input.session_id

  if not url or not question:
      raise HTTPException(status_code=400, detail="Both URL and question are required")
  
  try:
      response = chat_with_youtube(str(url), question, session_id)
      return {"output": response}
  except Exception as e:
      logger.error(f"Error in /chat-youtube endpoint: {e}")
      error_message = f"An error occurred while processing your request: {str(e)}. Please check the URL and try again."
      raise HTTPException(status_code=400, detail=error_message)

if __name__ == "__main__":
  import uvicorn
  uvicorn.run(app, host="0.0.0.0", port=5000)