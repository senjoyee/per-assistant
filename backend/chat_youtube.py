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
from dotenv import load_dotenv
from pydantic import HttpUrl
from langchain_community.document_loaders import YoutubeLoader

load_dotenv()

llm = ChatOpenAI(model="gpt-4-1106-preview", temperature=0)

def load_and_process_youtube(url: HttpUrl):
    print(f"Loading content from YouTube URL: {url}")
    try:
        loader = YoutubeLoader.from_youtube_url(url, add_video_info=True)
        documents = loader.load()

        text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
        splits = text_splitter.split_documents(documents)

        vectorstore = Chroma.from_documents(documents=splits, embedding=OpenAIEmbeddings())
        return vectorstore.as_retriever()
    except Exception as e:
        print(f"Error processing YouTube URL: {e}")
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
        "You are an assistant for question-answering tasks about YouTube videos. "
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

store = {}

def get_session_history(session_id: str) -> BaseChatMessageHistory:
    if session_id not in store:
        store[session_id] = ChatMessageHistory()
    return store[session_id]

def create_chain(url: str):
    retriever = load_and_process_youtube(url)
    if retriever is None:
        raise ValueError(f"Failed to process YouTube URL: {url}")
    
    rag_chain = create_rag_chain(retriever)
    
    return RunnableWithMessageHistory(
        rag_chain,
        get_session_history,
        input_messages_key="input",
        history_messages_key="chat_history",
        output_messages_key="answer",
    )

def chat_with_youtube(url: str, query: str, session_id: str):
    chain = create_chain(url)
    response = chain.invoke({"input": query}, config={"configurable": {"session_id": session_id}})
    return response["answer"]

if __name__ == "__main__":
    # Test the function
    video_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    query = "What is the main theme of this video?"
    session_id = "test_session"
    response = chat_with_youtube(video_url, query, session_id)
    print(response)