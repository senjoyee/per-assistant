from bs4 import BeautifulSoup
from langchain.chains import create_history_aware_retriever, create_retrieval_chain
from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain_chroma import Chroma
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
from langchain_community.chat_message_histories import ChatMessageHistory
from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.runnables.history import RunnableWithMessageHistory
from dotenv import load_dotenv
from pydantic import HttpUrl
import requests

load_dotenv()

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

def load_and_process_url(url: HttpUrl):
  print(f"Loading content from URL: {url}")
  try:
      response = requests.get(url)
      response.raise_for_status()
      soup = BeautifulSoup(response.text, "html.parser")
      main_content = soup.find("main") or soup.find("body")
      text_content = main_content.get_text(separator="\n", strip=True) if main_content else soup.get_text(separator="\n", strip=True)
      
      if not text_content:
          print(f"Warning: No content could be extracted from the URL: {url}")
          return None

      doc = Document(page_content=text_content, metadata={"source": str(url)})
      text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
      splits = text_splitter.split_documents([doc])

      vectorstore = Chroma.from_documents(documents=splits, embedding=OpenAIEmbeddings())
      return vectorstore.as_retriever()
  except Exception as e:
      print(f"Error processing URL: {e}")
      return None

def create_rag_chain(retriever):
  contextualize_q_system_prompt = (
      "Given a chat history and the latest user question "
      "which might reference context in the chat history, "
      "formulate a standalone question which can be understood "
      "without the chat history. Do NOT answer the question, "
      "just reformulate it if needed and otherwise return it as is."
  )
  contextualize_q_prompt = ChatPromptTemplate.from_messages(
      [
          ("system", contextualize_q_system_prompt),
          MessagesPlaceholder("chat_history"),
          ("human", "{input}"),
      ]
  )
  history_aware_retriever = create_history_aware_retriever(llm, retriever, contextualize_q_prompt)

  system_prompt = (
      "You are an assistant for question-answering tasks. "
      "Use the following pieces of retrieved context to answer "
      "the question. If you don't know the answer, say that you "
      "don't know. Use three sentences maximum and keep the "
      "answer concise."
      "\n\n"
      "{context}"
  )
  qa_prompt = ChatPromptTemplate.from_messages(
      [
          ("system", system_prompt),
          MessagesPlaceholder("chat_history"),
          ("human", "{input}"),
      ]
  )
  question_answer_chain = create_stuff_documents_chain(llm, qa_prompt)

  return create_retrieval_chain(history_aware_retriever, question_answer_chain)

store={}

def get_session_history(session_id: str) -> BaseChatMessageHistory:
    if session_id not in store:
        store[session_id] = ChatMessageHistory()
    return store[session_id]

def create_chain(url: str):
  retriever = load_and_process_url(url)
  if retriever is None:
      raise ValueError(f"Failed to process URL: {url}")
  
  rag_chain = create_rag_chain(retriever)
  
  return RunnableWithMessageHistory(
      rag_chain,
      get_session_history,  # We'll use an empty list for simplicity in this example
      input_messages_key="input",
      history_messages_key="chat_history",
      output_messages_key="answer",
  )

# Created/Modified files during execution:
print("chatbot.py")