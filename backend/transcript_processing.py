import os
from fastapi import UploadFile
from PyPDF2 import PdfReader
from docx import Document
from io import BytesIO
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

llm = ChatOpenAI(model="gpt-4o-mini")

async def extract_text_from_file(file: UploadFile) -> str:
    content = await file.read()
    file_extension = os.path.splitext(file.filename)[1].lower()
    
    if file_extension == '.pdf':
        return extract_text_from_pdf(content)
    elif file_extension in ['.doc', '.docx']:
        return extract_text_from_docx(content)
    elif file_extension == '.txt':
        return content.decode('utf-8')
    else:
        raise ValueError(f"Unsupported file format: {file_extension}")

def extract_text_from_pdf(content: bytes) -> str:
    pdf = PdfReader(BytesIO(content))
    return " ".join(page.extract_text() for page in pdf.pages)

def extract_text_from_docx(content: bytes) -> str:
    doc = Document(BytesIO(content))
    return " ".join(paragraph.text for paragraph in doc.paragraphs)

async def summarize_meeting_transcript(file: UploadFile) -> str:
    text = await extract_text_from_file(file)
    
    summary_template = """Analyze and summarize the following meeting transcript:
                        {text}
                        Provide a comprehensive summary in the following format:

                        OVERVIEW:

                        Brief summary of the meeting's purpose and overall content
                        Date, time, and duration of the meeting
                        List of attendees and their roles (if mentioned)


                        KEY POINTS:

                        Main topics discussed, listed in order of importance
                        Highlight any critical updates or announcements
                        Summarize significant contributions or ideas from key participants


                        ACTION ITEMS:

                        List all tasks, assignments, or follow-ups decided in the meeting
                        Include who is responsible for each action item
                        Specify deadlines or timeframes, if mentioned
                        Prioritize tasks if possible


                        DECISIONS:

                        Enumerate all decisions made during the meeting
                        Provide context for each decision (why it was made, its impact)
                        Note any dissenting opinions or concerns raised


                        PROJECT UPDATES:

                        Summarize progress reports on ongoing projects
                        Highlight any changes in project timelines, scope, or resources


                        CHALLENGES AND RISKS:

                        Identify any obstacles, risks, or concerns discussed
                        Outline proposed solutions or mitigation strategies


                        KEY METRICS:

                        List any important numbers, statistics, or KPIs mentioned
                        Provide context for these metrics if available


                        NEXT STEPS:

                        Outline agreed-upon future plans or strategies
                        Note the date and time of the next meeting, if mentioned


                        OPEN QUESTIONS:

                        List any unanswered questions or unresolved issues
                        Note areas where further discussion or information is needed


                        ADDITIONAL NOTES:

                        Any other relevant information that doesn't fit into the above categories
                        Notable quotes or key phrases, if any



                        Please ensure the summary is clear, concise, and easily scannable. Use bullet points where appropriate. If certain information is not available in the transcript, indicate that it was not discussed or mentioned.
    """
    
    summary_prompt = ChatPromptTemplate.from_template(summary_template)
    summary_chain = summary_prompt | llm | StrOutputParser()
    
    summary = await summary_chain.ainvoke({"text": text})
    return summary

async def chat_with_meeting_transcript(file: UploadFile, question: str, session_id: str) -> str:
    text = await extract_text_from_file(file)
    
    chat_template = """Use the following meeting transcript to answer the question:
    {text}
    
    Question: {question}
    
    Provide a concise and relevant answer based on the transcript content.
    """
    
    chat_prompt = ChatPromptTemplate.from_template(chat_template)
    chat_chain = chat_prompt | llm | StrOutputParser()
    
    answer = await chat_chain.ainvoke({"text": text, "question": question})
    return answer