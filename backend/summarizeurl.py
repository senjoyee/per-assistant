import requests
from bs4 import BeautifulSoup
from langchain_openai import ChatOpenAI
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langgraph.graph import StateGraph, END, START
from langgraph.constants import Send
import operator
from typing import Annotated, List, TypedDict, Literal
from dotenv import load_dotenv
from langchain.chains.combine_documents.reduce import acollapse_docs, split_list_of_docs
from langchain_core.runnables import RunnableLambda
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Initialize the LLM
llm = ChatOpenAI(model="gpt-4o-mini")

# Define the text splitter
text_splitter = RecursiveCharacterTextSplitter(chunk_size=2000, chunk_overlap=200)

# Define prompts
map_template = """Analyze the following chunk of content from a web page and provide a detailed summary. Your summary should include the following sections:
  1. SUMMARY: In 50 words or less, provide an overview of the content, including the main topics discussed.
  2. IDEAS: List the top ideas presented in this chunk. 
  3. QUOTES: Extract the most insightful and interesting quotes from this chunk. Use the exact quote text.
  4. FACTS: List interesting and valid facts about the greater world that were mentioned in this chunk.
  5. RECOMMENDATIONS: Provide insightful and interesting recommendations that can be derived from this chunk of content.
  Ensure that your summary is comprehensive and captures the essence of this specific chunk of content.
  {context}"""

reduce_template = """The following is a set of summaries from a web page:{docs}
  Your task is to synthesize these summaries into a comprehensive overview of the entire content. Create a final summary with the following sections:
  1. SUMMARY: In 50 words or less, provide an overarching summary of the entire content, including the key themes discussed across all chunks.
  2. IDEAS: Compile and synthesize the top ideas from all the chunks. If there are recurring ideas, consolidate them and prioritize based on importance and frequency of mention.
  3. QUOTES: Select the most impactful and insightful quotes from all the chunks. Ensure these quotes represent the breadth of the content.
  4. FACTS: Synthesize the most interesting and significant facts about the greater world that were mentioned throughout the content.
  5. REFERENCES: Compile a comprehensive list of all writings, artworks, and other sources of inspiration mentioned across all chunks. Organize these references by type or relevance.
  6. RECOMMENDATIONS: Provide the most insightful and actionable recommendations derived from the entire content. Prioritize recommendations that appeared in multiple chunks or seem particularly impactful.
  Your final summary should provide a cohesive overview of the entire content, highlighting the most important and recurring themes, ideas, and insights across all chunks.
  """

map_prompt = ChatPromptTemplate([("human", map_template)])
reduce_prompt = ChatPromptTemplate([("human", reduce_template)])

map_chain = map_prompt | llm | StrOutputParser()
reduce_chain = reduce_prompt | llm | StrOutputParser()

# Define state types
class OverallState(TypedDict):
  contents: List[str]
  summaries: Annotated[list, operator.add]
  collapsed_summaries: List[Document]
  final_summary: str

class SummaryState(TypedDict):
  content: str

# Define functions
async def generate_summary(state: SummaryState):
  response = await map_chain.ainvoke({"context": state["content"]})
  return {"summaries": [response]}

def map_summaries(state: OverallState):
  return [
      Send("generate_summary", {"content": content}) for content in state["contents"]
  ]

def collect_summaries(state: OverallState):
  return {
      "collapsed_summaries": [
          Document(page_content=summary) for summary in state["summaries"]
      ]
  }

async def generate_final_summary(state: OverallState):
  response = await reduce_chain.ainvoke(
      {"docs": "\n".join([doc.page_content for doc in state["collapsed_summaries"]])}
  )
  return {"final_summary": response}

# Define length_function and token_max
def length_function(documents: List[Document]) -> int:
  return sum(len(doc.page_content.split()) for doc in documents)

token_max = 4000  # Adjust this value based on your needs

async def collapse_summaries(state: OverallState):
  doc_lists = split_list_of_docs(
      state["collapsed_summaries"], length_function, token_max
  )
  results = []
  for doc_list in doc_lists:
      results.append(
          await acollapse_docs(doc_list, lambda x: reduce_chain.ainvoke({"docs": x}))
      )
  return {"collapsed_summaries": results}

def should_collapse(
  state: OverallState,
) -> Literal["collapse_summaries", "generate_final_summary"]:
  num_tokens = length_function(state["collapsed_summaries"])
  if num_tokens > token_max:
      return "collapse_summaries"
  else:
      return "generate_final_summary"

# Set up the graph
graph = StateGraph(OverallState)
graph.add_node("generate_summary", generate_summary)
graph.add_node("collect_summaries", collect_summaries)
graph.add_node("generate_final_summary", generate_final_summary)
graph.add_node("collapse_summaries", collapse_summaries)
graph.add_conditional_edges(START, map_summaries, ["generate_summary"])
graph.add_edge("generate_summary", "collect_summaries")
graph.add_conditional_edges("collect_summaries", should_collapse)
graph.add_conditional_edges("collapse_summaries", should_collapse)
graph.add_edge("generate_final_summary", END)
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
      async for step in app.astream(
          {"contents": [doc.page_content for doc in doc_chunks]},
          {"recursion_limit": 100},
      ):
          if "final_summary" in step.get("generate_final_summary", {}):
              logger.info("Final summary generated successfully")
              return step["generate_final_summary"]["final_summary"]

      logger.warning("Failed to generate summary")
      return "Failed to generate summary."
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