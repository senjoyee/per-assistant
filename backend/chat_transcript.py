from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnableWithMessageHistory
from langchain_community.chat_message_histories import ChatMessageHistory
from langchain_core.chat_history import BaseChatMessageHistory
from dotenv import load_dotenv
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

chat_template = """Use the following meeting transcript to answer the question:
{text}

Question: {input}

Provide a concise and relevant answer based on the transcript content.
"""

chat_prompt = ChatPromptTemplate.from_template(chat_template)
chat_chain = chat_prompt | llm | StrOutputParser()

store = {}

def get_session_history(session_id: str) -> BaseChatMessageHistory:
  if session_id not in store:
      store[session_id] = ChatMessageHistory()
  return store[session_id]

def create_chain(text: str):
  return RunnableWithMessageHistory(
      chat_chain,
      get_session_history,
      input_messages_key="input",
      history_messages_key="chat_history",
  ).with_config({"configurable": {"text": text}})

async def chat_with_meeting_transcript(text: str, question: str, session_id: str) -> str:
  logger.info(f"Starting chat with meeting transcript for session: {session_id}")
  try:
      chain = create_chain(text)
      response = await chain.ainvoke(
          {"input": question},
          config={"configurable": {"session_id": session_id}}
      )
      logger.info("Successfully generated response")
      return response
  except Exception as e:
      logger.error(f"Error in chat_with_meeting_transcript: {str(e)}", exc_info=True)
      raise

# Create a RunnableAsync instance
chat_with_meeting_transcript_runnable = RunnableWithMessageHistory(
  chat_chain,
  get_session_history,
  input_messages_key="input",
  history_messages_key="chat_history",
)