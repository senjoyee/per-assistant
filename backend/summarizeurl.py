import requests
from bs4 import BeautifulSoup
from langchain_openai import ChatOpenAI
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langgraph.graph import StateGraph, END, START
from typing import List, TypedDict, Literal
from dotenv import load_dotenv
from langchain_core.runnables import RunnableLambda, RunnableConfig
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Initialize the LLM
llm = ChatOpenAI(model="gpt-4o-mini")

# Define the text splitter
text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=50)

# Define prompts
initial_summary_template = """Analyze the following chunk of content from a web page and provide a detailed summary. Your summary should include the following sections:
1. SUMMARY: In 50 words or less, provide an overview of the content, including the main topics discussed.
2. IDEAS: List the top ideas presented in this chunk. 
3. QUOTES: Extract the most insightful and interesting quotes from this chunk. Use the exact quote text.
4. FACTS: List interesting and valid facts about the greater world that were mentioned in this chunk.
5. RECOMMENDATIONS: Provide insightful and interesting recommendations that can be derived from this chunk of content.
Ensure that your summary is comprehensive and captures the essence of this specific chunk of content.

Content:
{context}"""

refine_template = """Refine the existing summary with new information from the web page. Maintain the following structure:

1. SUMMARY: In 50 words or less, provide an overarching summary of the entire content, including the key themes discussed across all chunks.
2. IDEAS: Compile and synthesize the top ideas from all the chunks. If there are recurring ideas, consolidate them and prioritize based on importance and frequency of mention.
3. QUOTES: Select the most impactful and insightful quotes from all the chunks. Ensure these quotes represent the breadth of the content.
4. FACTS: Synthesize the most interesting and significant facts about the greater world that were mentioned throughout the content.
5. REFERENCES: Compile a comprehensive list of all writings, artworks, and other sources of inspiration mentioned across all chunks. Organize these references by type or relevance.
6. RECOMMENDATIONS: Provide the most insightful and actionable recommendations derived from the entire content. Prioritize recommendations that appeared in multiple chunks or seem particularly impactful.

Existing summary:
{existing_summary}

New content to incorporate:
{context}

Provide an updated summary that integrates the new information while maintaining the overall structure and quality."""

initial_summary_prompt = ChatPromptTemplate.from_template(initial_summary_template)
refine_prompt = ChatPromptTemplate.from_template(refine_template)

initial_summary_chain = initial_summary_prompt | llm | StrOutputParser()
refine_summary_chain = refine_prompt | llm | StrOutputParser()

# Define state types
class State(TypedDict):
  contents: List[str]
  index: int
  summary: str

# Define functions
async def generate_initial_summary(state: State, config: RunnableConfig):
  summary = await initial_summary_chain.ainvoke(
      {"context": state["contents"][0]},
      config,
  )
  return {"summary": summary, "index": 1}

async def refine_summary(state: State, config: RunnableConfig):
  content = state["contents"][state["index"]]
  summary = await refine_summary_chain.ainvoke(
      {"existing_summary": state["summary"], "context": content},
      config,
  )
  return {"summary": summary, "index": state["index"] + 1}

def should_refine(state: State) -> Literal["refine_summary", END]:
  if state["index"] >= len(state["contents"]):
      return END
  else:
      return "refine_summary"

# Set up the graph
graph = StateGraph(State)
graph.add_node("generate_initial_summary", generate_initial_summary)
graph.add_node("refine_summary", refine_summary)

graph.add_edge(START, "generate_initial_summary")
graph.add_conditional_edges("generate_initial_summary", should_refine)
graph.add_conditional_edges("refine_summary", should_refine)
app = graph.compile()

# Main function
async def summarize_url(url: str) -> str:
  logger.info(f"Starting summarization for URL: {url}")
  try:
      # Fetch and parse the web page
      response = requests.get(url)
      response.raise_for_status()
      soup = BeautifulSoup(response.text, "html.parser")

      # Extract text from the main content area
      main_content = soup.find("main") or soup.find("body")
      if main_content:
          text_content = main_content.get_text(separator="\n", strip=True)
      else:
          text_content = soup.get_text(separator="\n", strip=True)

      # Split the content into chunks
      doc = Document(page_content=text_content, metadata={"source": url})
      doc_chunks = text_splitter.split_documents([doc])
      logger.info(f"Split document into {len(doc_chunks)} chunks")

      # Process the chunks and generate the final summary
      result = await app.ainvoke(
          {"contents": [doc.page_content for doc in doc_chunks]},
          {"recursion_limit": 100},
      )
      
      logger.info("Final summary generated successfully")
      return result["summary"]
  except Exception as e:
      logger.error(f"Error in summarize_url: {str(e)}", exc_info=True)
      raise

# Create a RunnableAsync instance
summarize_url_runnable = RunnableLambda(summarize_url)

if __name__ == "__main__":
  # Test the function
  import asyncio
  test_url = "https://example.com"
  summary = asyncio.run(summarize_url(test_url))
  print(summary)