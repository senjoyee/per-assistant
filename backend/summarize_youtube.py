from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_community.document_loaders import YoutubeLoader
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter,NLTKTextSplitter
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langgraph.graph import StateGraph, END, START
from langgraph.constants import Send
import operator
from typing import Annotated, List, TypedDict, Literal
from langchain.chains.combine_documents.reduce import acollapse_docs, split_list_of_docs
from langchain_core.runnables import RunnableLambda
import logging
import re
import asyncio
import time
import openai
from youtube_transcript_api import YouTubeTranscriptApi
import time
from tenacity import retry, wait_exponential, stop_after_attempt


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Initialize the LLM
llm = ChatOpenAI(model="gpt-4o-mini")

# Define the text splitter
text_splitter = RecursiveCharacterTextSplitter(chunk_size=10000, chunk_overlap=1000)

# Define prompts
map_template = """Analyze the following chunk of content from a YouTube video transcript and provide a detailed summary. Your summary should be as comprehensive as possible, capturing all relevant information. Include the following sections:

                1. CHUNK OVERVIEW: Provide a concise overview of this specific chunk, including speakers (if identifiable) and main topics discussed.

                2. KEY POINTS: List and explain in detail all main points or arguments presented in this chunk. Do not summarize or condense information; instead, elaborate on each point thoroughly.

                3. IDEAS AND CONCEPTS: Identify and elaborate on all ideas and concepts introduced or discussed in this section. Explain their significance and any connections to broader themes.

                4. QUOTES: Extract all relevant quotes from this chunk. Include speaker attribution if available, and provide context for each quote.

                5. FACTS AND STATISTICS: List all specific facts, statistics, or data points mentioned, with full context and explanation.

                6. EXAMPLES AND ANECDOTES: Fully summarize any examples or anecdotes used, explaining their relevance to the main points.

                7. TECHNICAL TERMS: Define and explain any specialized or technical terms introduced in this chunk, providing context for their use.

                8. CONTROVERSIES OR DEBATES: Highlight and explain any contentious points or ongoing debates mentioned, providing all relevant perspectives presented.

                9. HISTORICAL OR CULTURAL REFERENCES: Note and explain any historical events or cultural references made, providing necessary background information.

                10. IMPLICATIONS AND RECOMMENDATIONS: Identify any explicit recommendations or implied consequences of the ideas presented. Elaborate on potential applications or impacts.

                11. CONNECTIONS: Note any connections made to other topics, fields, or previous points in the video. Explain these connections in detail.

                12. QUESTIONS AND UNCERTAINTIES: List any questions posed or areas of uncertainty highlighted in this section. Include any calls for further research or investigation.

                Ensure your summary captures all the nuances and details of this specific chunk of content. Do not omit any significant information; the goal is to provide a comprehensive account of this portion of the transcript.
                {context}"""


reduce_template = """The following is a set of summaries from a YouTube video transcript:{docs}
                    You are tasked with synthesizing a set of detailed summaries from a YouTube video transcript into a comprehensive overview. Your final summary should be as detailed and extensive as the original content, reflecting its full depth and complexity. Do not aim to condense the information, but rather to reorganize and present it coherently. Structure your summary with the following sections:

                    1. CONTENT OVERVIEW: Provide a thorough overview of the entire content, including main presenters, key themes, and the video's overall purpose or message. Describe the structure of the video and how ideas progress throughout.

                    2. KEY ARGUMENTS AND IDEAS: Compile and synthesize all ideas and arguments from the chunks. Identify recurring themes, contradictions, and how ideas evolve or are reinforced throughout the video. Explain each idea in detail.

                    3. DETAILED DISCUSSION OF MAIN TOPICS: For each main topic covered in the video, provide an in-depth discussion. Include all relevant points, arguments, and supporting evidence presented.

                    4. QUOTES: Include all significant quotes from the video. Provide context for each quote, explain its significance, and attribute it to the speaker if known.

                    5. FACTS AND STATISTICS: Compile a comprehensive list of all facts, statistics, and data points mentioned. Provide full context and explanation for each item.

                    6. EXAMPLES AND CASE STUDIES: Thoroughly summarize all examples, case studies, or anecdotes used to illustrate points in the video. Explain their relevance and implications.

                    7. TECHNICAL CONCEPTS: Define and explain all specialized or technical terms introduced, providing context for their use in the video and their broader significance if applicable.

                    8. CONTROVERSIES AND DEBATES: Outline all contentious points, ongoing debates, or areas of disagreement discussed in the video. Present all perspectives provided and explain the implications of these debates.

                    9. HISTORICAL AND CULTURAL CONTEXT: Synthesize all historical events, cultural references, or contextual information provided throughout the video. Explain their relevance to the main topics.

                    10. IMPLICATIONS AND FUTURE DIRECTIONS: Discuss all implications of the ideas presented and any future directions or areas for further exploration suggested in the video.

                    11. CONNECTIONS AND INTERDISCIPLINARY LINKS: Highlight all connections made to other fields, disciplines, or broader themes beyond the main topic. Explain these connections in detail.

                    12. CRITICAL ANALYSIS: Provide a balanced critique of the content, considering strengths, weaknesses, potential biases, and areas where more evidence or explanation might be needed. Base this analysis on the information provided in the video.

                    13. QUESTIONS AND AREAS FOR FURTHER RESEARCH: Compile a comprehensive list of all questions raised or areas of uncertainty highlighted in the video, as well as potential areas for further research or investigation mentioned.

                    14. REFERENCES AND RESOURCES: Compile a complete list of all writings, artworks, studies, or other sources mentioned or referenced in the video. Provide context for why each source was mentioned.

                    15. ACTIONABLE INSIGHTS: Provide all insights and recommendations derived from the content. Explain each recommendation and its potential impact or application.

                    Your final summary should provide a cohesive, detailed, and nuanced overview of the entire content, capturing all significant information presented in the video. The goal is to create a comprehensive resource that includes all the valuable content from the video, organized for clarity but not reduced in scope or detail.
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

#Rate limit
@retry(wait=wait_exponential(multiplier=1, min=4, max=10), stop=stop_after_attempt(5))
async def rate_limited_generate_summary(content: str):
  try:
      return await map_chain.ainvoke({"context": content})
  except openai.RateLimitError as e:
      logger.warning(f"Rate limit reached. Retrying in a moment...")
      time.sleep(1)  # Sleep for a second before retrying
      raise e

async def generate_summary(state: SummaryState):
  response = await rate_limited_generate_summary(state["content"])
  return {"summaries": [response]}

# Define functions
async def generate_summary(state: SummaryState):
    max_retries = 5
    for attempt in range(max_retries):
        try:
            response = await map_chain.ainvoke({"context": state["content"]})
            return {"summaries": [response]}
        except openai.RateLimitError as e:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # exponential backoff
                logger.warning(f"Rate limit reached. Waiting for {wait_time} seconds before retrying.")
                await asyncio.sleep(wait_time)
            else:
                raise e

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

token_max = 10000  # Adjust this value based on your needs

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

def process_subtitle_data(subtitle_data):
  # Remove time stamps and other non-text content
  cleaned_text = re.sub(r'\d{2}:\d{2}:\d{2},\d{3} --> \d{2}:\d{2}:\d{2},\d{3}', '', subtitle_data)
  cleaned_text = re.sub(r'\n\n', ' ', cleaned_text)
  return cleaned_text.strip()

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

# Custom YouTube loader using yt-dlp
def load_youtube_video(url: str) -> List[Document]:
  video_id = url.split("v=")[1]
  try:
      transcript = YouTubeTranscriptApi.get_transcript(video_id)
      full_transcript = " ".join([entry['text'] for entry in transcript])
      return [Document(page_content=full_transcript, metadata={"source": url})]
  except Exception as e:
      logger.error(f"Error fetching transcript: {str(e)}")
      raise
  
# Main function
async def summarize_youtube_video(url: str) -> str:
  logger.info(f"Starting summarization for YouTube URL: {url}")
  try:
      docs = load_youtube_video(url)
      logger.info(f"Loaded {len(docs)} documents from YouTube")
      doc_chunks = text_splitter.split_documents(docs)
      logger.info(f"Split documents into {len(doc_chunks)} chunks")

      summaries = []
      batch_size = 5  # Process 5 chunks at a time
      for i in range(0, len(doc_chunks), batch_size):
          batch = doc_chunks[i:i+batch_size]
          tasks = [generate_summary({"content": chunk.page_content}) for chunk in batch]
          batch_results = await asyncio.gather(*tasks)
          summaries.extend([result["summaries"][0] for result in batch_results])
          logger.info(f"Processed batch {i//batch_size + 1}/{len(doc_chunks)//batch_size + 1}")
          time.sleep(1)  # Add a small delay between batches

      final_summary = await reduce_chain.ainvoke({"docs": "\n".join(summaries)})
      logger.info("Final summary generated successfully")
      return final_summary

  except Exception as e:
      logger.error(f"Error in summarize_youtube_video: {str(e)}", exc_info=True)
      raise

# Create a RunnableAsync instance
summarize_youtube_video_runnable = RunnableLambda(summarize_youtube_video)

if __name__ == "__main__":
    # Test the function
    import asyncio
    video_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    summary = asyncio.run(summarize_youtube_video(video_url))
    print(summary)