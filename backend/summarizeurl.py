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

# Load environment variables
load_dotenv()

# Initialize the LLM
llm = ChatOpenAI(model="gpt-4o-mini")

# Define the text splitter
text_splitter = RecursiveCharacterTextSplitter(chunk_size=2000, chunk_overlap=200)

# Define prompts
map_template = "Write a concise summary of the following: {context}."
reduce_template = """
The following is a set of summaries:
{docs}
Based on these summaries, create a concise point-wise summary of the main themes. Please follow these guidelines:

1. Identify the key themes or topics that appear across multiple summaries.
2. For each main theme, create a bullet point.
3. Under each bullet point, add 1-3 sub-points that provide supporting details or examples.
4. Ensure that each point is clear, concise, and directly related to the information in the summaries.
5. Avoid repetition and focus on the most important information.
6. Limit the summary to a maximum of 5-7 main bullet points.

Your output should be in the following format:

• Main Theme 1
  - Supporting detail or example
  - Additional supporting detail (if applicable)

• Main Theme 2
  - Supporting detail or example
  - Additional supporting detail (if applicable)

(and so on...)
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
async def summarize_url(url):
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

    # Process the chunks and generate the final summary
    async for step in app.astream(
        {"contents": [doc.page_content for doc in doc_chunks]},
        {"recursion_limit": 10},
    ):
        if "final_summary" in step.get("generate_final_summary", {}):
            return step["generate_final_summary"]["final_summary"]

    return "Failed to generate summary."


# Create a RunnableAsync instance
summarize_url_runnable = RunnableLambda(summarize_url)
