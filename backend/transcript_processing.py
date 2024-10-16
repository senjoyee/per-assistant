import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langgraph.graph import StateGraph, END, START
from langgraph.constants import Send
import operator
from typing import Annotated, List, TypedDict, Literal
from langchain.chains.combine_documents.reduce import acollapse_docs, split_list_of_docs
from langchain_core.runnables import RunnableLambda
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

llm = ChatOpenAI(model="gpt-4o-mini")
text_splitter = RecursiveCharacterTextSplitter(chunk_size=2000, chunk_overlap=200)

# Define prompts, state types, and functions here

map_template = """Analyze the following chunk of a meeting transcript and provide a detailed summary. Your summary should include the following sections:
  1. OVERVIEW: In 50 words or less, provide an overview of this chunk's content.
  2. KEY POINTS: List the main topics discussed in this chunk.
  3. ACTION ITEMS: List tasks, assignments, or follow-ups decided in this chunk. Include who is responsible and deadlines if mentioned.
  4. DECISIONS: Enumerate decisions made during this part of the meeting. Provide context for each decision.
  5. ADDITIONAL NOTES: Any other relevant information from this chunk.
  Ensure that your summary is comprehensive and captures the essence of this specific chunk of content.
  {context}"""

reduce_template = """The following is a set of summaries from a meeting transcript:{docs}
  Your task is to synthesize these summaries into a comprehensive overview of the entire meeting. Create a final summary with the following sections:
  1. OVERVIEW: In 50 words or less, provide an overarching summary of the entire meeting, including the key themes discussed across all chunks.
  2. KEY POINTS: Compile and synthesize the main topics from all the chunks. If there are recurring topics, consolidate them and prioritize based on importance and frequency of mention.
  3. ACTION ITEMS: Compile a comprehensive list of all tasks, assignments, and follow-ups decided during the meeting. Include who is responsible and deadlines for each item.
  4. DECISIONS: Synthesize all decisions made during the meeting. Provide context for each decision and organize them logically.
  5. ADDITIONAL NOTES: Include any other relevant information that doesn't fit into the above categories but is important for understanding the meeting's outcomes.
  Your final summary should provide a cohesive overview of the entire meeting, highlighting the most important and recurring themes, decisions, and action items across all chunks.
  """

map_prompt = ChatPromptTemplate([("human", map_template)])
reduce_prompt = ChatPromptTemplate([("human", reduce_template)])

map_chain = map_prompt | llm | StrOutputParser()
reduce_chain = reduce_prompt | llm | StrOutputParser()

class OverallState(TypedDict):
  contents: List[str]
  summaries: Annotated[list, operator.add]
  collapsed_summaries: List[Document]
  final_summary: str

class SummaryState(TypedDict):
  content: str

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

def length_function(documents: List[Document]) -> int:
  return sum(len(doc.page_content.split()) for doc in documents)

token_max = 4000

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
  
class OverallState(TypedDict):
  contents: List[str]
  summaries: Annotated[list, operator.add]
  collapsed_summaries: List[Document]
  final_summary: str

class SummaryState(TypedDict):
  content: str

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

def length_function(documents: List[Document]) -> int:
  return sum(len(doc.page_content.split()) for doc in documents)

token_max = 4000

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

async def summarize_meeting_transcript(file_content: str) -> str:
  logger.info("Starting meeting transcript summarization")
  try:
      # Split the content into chunks
      doc_chunks = text_splitter.split_text(file_content)
      logger.info(f"Split transcript into {len(doc_chunks)} chunks")

      # Process the chunks and generate the final summary
      async for step in app.astream(
          {"contents": doc_chunks},
          {"recursion_limit": 100},
      ):
          if "final_summary" in step.get("generate_final_summary", {}):
              logger.info("Final summary generated successfully")
              return step["generate_final_summary"]["final_summary"]

      logger.warning("Failed to generate summary")
      return "Failed to generate summary."
  except Exception as e:
      logger.error(f"Error in summarize_meeting_transcript: {str(e)}", exc_info=True)
      raise

# Create a RunnableAsync instance
summarize_meeting_transcript_runnable = RunnableLambda(summarize_meeting_transcript)


