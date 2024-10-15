"use client";

import React, { useState, useEffect, useRef } from 'react'
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle, CardFooter } from "@/components/ui/card"
import { Label } from "@/components/ui/label"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import { Globe, Loader2, Send, Youtube, FileText, Upload } from 'lucide-react'
import axios from 'axios';
import { v4 as uuidv4 } from 'uuid';
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"

function generateSessionId(): string {
  return uuidv4();
}

interface Message {
  role: 'user' | 'assistant';
  content: string;
}

const cleanContent = (content: string): string => {
  return content
    .replace(/\*\*/g, '')
    .replace(/###/g, '')
    .replace(/^#+\s*/gm, '')
    .trim();
};

const formatMessageContent = (content: string): React.ReactNode => {
  return content.split('\n').map((line, index) => (
    <React.Fragment key={index}>
      {line}
      {index < content.split('\n').length - 1 && <br />}
    </React.Fragment>
  ));
};

export default function AIAssistant() {
  const [activeTab, setActiveTab] = useState<'web' | 'youtube' | 'transcript'>('web')
  const [url, setUrl] = useState('')
  const [youtubeUrl, setYoutubeUrl] = useState('')
  const [transcriptFile, setTranscriptFile] = useState<File | null>(null)
  const [currentUrl, setCurrentUrl] = useState('');
  const sessionId = generateSessionId();
  const [question, setQuestion] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [chatMessages, setChatMessages] = useState<Message[]>([])
  const [summary, setSummary] = useState('')
  const [isChatVisible, setIsChatVisible] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setChatMessages([]);
    setIsChatVisible(false);
    setSummary('');
  }, [url, youtubeUrl, transcriptFile]);

  const handleSummarize = async () => {
    let currentUrl = '';
    let endpoint = '';
    let payload: any = {};

    if (activeTab === 'web') {
      currentUrl = url;
      endpoint = 'summarize';
      payload = { url: currentUrl };
    } else if (activeTab === 'youtube') {
      currentUrl = youtubeUrl;
      endpoint = 'summarize-youtube';
      payload = { url: currentUrl };
    } else if (activeTab === 'transcript' && transcriptFile) {
      endpoint = 'summarize-transcript';
      const formData = new FormData();
      formData.append('file', transcriptFile);
      payload = formData;
    }

    if (!currentUrl && !transcriptFile) return;
    setIsLoading(true);
    try {
      const response = await axios.post(`http://localhost:5000/${endpoint}`, payload, {
        headers: {
          'Content-Type': activeTab === 'transcript' ? 'multipart/form-data' : 'application/json',
        },
      });
      setSummary(cleanContent(response.data.output));
      setCurrentUrl(currentUrl);
    } catch (error) {
      console.error('Error summarizing:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const handleStartChat = () => {
    setIsChatVisible(true);
    if (chatMessages.length === 0) {
      setChatMessages([{ role: 'assistant', content: `What would you like to know about this ${activeTab === 'web' ? 'web page' : activeTab === 'youtube' ? 'YouTube video' : 'meeting transcript'}?` }]);
    }
  };

  const handleAskQuestion = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!question) return;
    setIsLoading(true);
    setChatMessages(prev => [...prev, { role: 'user', content: question }]);
    try {
      let endpoint = '';
      let payload: any = {};

      if (activeTab === 'web') {
        endpoint = 'chat';
        payload = { question, url, session_id: sessionId };
      } else if (activeTab === 'youtube') {
        endpoint = 'chat-youtube';
        payload = { question, url: youtubeUrl, session_id: sessionId };
      } else if (activeTab === 'transcript') {
        endpoint = 'chat-transcript';
        const formData = new FormData();
        formData.append('question', question);
        formData.append('session_id', sessionId);
        if (transcriptFile) {
          formData.append('file', transcriptFile);
        }
        payload = formData;
      }

      const response = await axios.post(`http://localhost:5000/${endpoint}`, payload, {
        headers: {
          'Content-Type': activeTab === 'transcript' ? 'multipart/form-data' : 'application/json',
        },
      });
      setChatMessages(prev => [...prev, { role: 'assistant', content: response.data.output }]);
    } catch (error) {
      console.error('Error answering question:', error);
      let errorMessage = `An error occurred while processing your question about the ${activeTab === 'web' ? 'web page' : activeTab === 'youtube' ? 'YouTube video' : 'meeting transcript'}.`;
      if (axios.isAxiosError(error) && error.response?.data?.detail) {
        errorMessage = error.response.data.detail;
      }
      setChatMessages(prev => [...prev, { role: 'assistant', content: errorMessage }]);
    } finally {
      setIsLoading(false);
      setQuestion('');
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setTranscriptFile(e.target.files[0]);
    }
  };

  const handleUploadClick = () => {
    fileInputRef.current?.click();
  };

  return (
    <div className="container mx-auto p-4 bg-gray-900 text-gray-100 min-h-screen">
      <h1 className="text-2xl font-normal mb-6 text-cyan-400 font-work-sans">AI Assistant</h1>
      <Tabs value={activeTab} onValueChange={(value) => setActiveTab(value as 'web' | 'youtube' | 'transcript')} className="w-full">
        <TabsList className="grid w-full grid-cols-3">
          <TabsTrigger value="web">Web URL</TabsTrigger>
          <TabsTrigger value="youtube">YouTube</TabsTrigger>
          <TabsTrigger value="transcript">Meeting Transcript</TabsTrigger>
        </TabsList>
        <TabsContent value="web">
          <Card className="bg-gray-800 border-gray-700 mb-6 rounded-lg overflow-hidden">
            <CardHeader className="bg-gray-750">
              <CardTitle className="text-cyan-400 font-work-sans font-normal">Web Page Interaction</CardTitle>
            </CardHeader>
            <CardContent className="pt-6">
              <div className="flex flex-col space-y-1.5">
                <Label htmlFor="url" className="text-gray-300">Web Page URL</Label>
                <div className="flex space-x-2">
                  <Input 
                    id="url" 
                    placeholder="Enter URL" 
                    value={url} 
                    onChange={(e) => setUrl(e.target.value)} 
                    className="flex-grow bg-gray-700 text-white border-gray-600 rounded-md"
                  />
                  <Button 
                    onClick={handleSummarize} 
                    disabled={isLoading || !url} 
                    className="bg-cyan-600 text-white hover:bg-cyan-700 rounded-md"
                  >
                    {isLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Globe className="h-4 w-4 mr-2" />}
                    Summarize
                  </Button>
                  <Button 
                    onClick={handleStartChat} 
                    disabled={!url}
                    className="bg-cyan-600 text-white hover:bg-cyan-700 rounded-md"
                  >
                    Chat
                  </Button>
                </div>
              </div>
              {url && (
                <p className="mt-2 text-sm text-gray-400">Current URL: {url}</p>
              )}
            </CardContent>
          </Card>
        </TabsContent>
        <TabsContent value="youtube">
          <Card className="bg-gray-800 border-gray-700 mb-6 rounded-lg overflow-hidden">
            <CardHeader className="bg-gray-750">
              <CardTitle className="text-cyan-400 font-work-sans font-normal">YouTube Video Interaction</CardTitle>
            </CardHeader>
            <CardContent className="pt-6">
              <div className="flex flex-col space-y-1.5">
                <Label htmlFor="youtubeUrl" className="text-gray-300">YouTube Video URL</Label>
                <div className="flex space-x-2">
                  <Input 
                    id="youtubeUrl" 
                    placeholder="Enter YouTube URL" 
                    value={youtubeUrl} 
                    onChange={(e) => setYoutubeUrl(e.target.value)} 
                    className="flex-grow bg-gray-700 text-white border-gray-600 rounded-md"
                  />
                  <Button 
                    onClick={handleSummarize} 
                    disabled={isLoading || !youtubeUrl} 
                    className="bg-cyan-600 text-white hover:bg-cyan-700 rounded-md"
                  >
                    {isLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Youtube className="h-4 w-4 mr-2" />}
                    Summarize
                  </Button>
                  <Button 
                    onClick={handleStartChat} 
                    disabled={!youtubeUrl}
                    className="bg-cyan-600 text-white hover:bg-cyan-700 rounded-md"
                  >
                    Chat
                  </Button>
                </div>
              </div>
              {youtubeUrl && (
                <p className="mt-2 text-sm text-gray-400">Current YouTube URL: {youtubeUrl}</p>
              )}
            </CardContent>
          </Card>
        </TabsContent>
        <TabsContent value="transcript">
          <Card className="bg-gray-800 border-gray-700 mb-6 rounded-lg overflow-hidden">
            <CardHeader className="bg-gray-750">
              <CardTitle className="text-cyan-400 font-work-sans font-normal">Meeting Transcript Interaction</CardTitle>
            </CardHeader>
            <CardContent className="pt-6">
              <div className="flex flex-col space-y-1.5">
                <Label htmlFor="transcriptFile" className="text-gray-300">Upload Transcript File</Label>
                <div className="flex space-x-2">
                  <input
                    type="file"
                    id="transcriptFile"
                    ref={fileInputRef}
                    onChange={handleFileChange}
                    className="hidden"
                    accept=".txt,.doc,.docx,.pdf"
                  />
                  <Button 
                    onClick={handleUploadClick}
                    className="bg-gray-700 text-white hover:bg-gray-600 rounded-md flex-grow"
                  >
                    <Upload className="h-4 w-4 mr-2" />
                    {transcriptFile ? transcriptFile.name : "Choose file"}
                  </Button>
                  <Button 
                    onClick={handleSummarize} 
                    disabled={isLoading || !transcriptFile} 
                    className="bg-cyan-600 text-white hover:bg-cyan-700 rounded-md"
                  >
                    {isLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileText className="h-4 w-4 mr-2" />}
                    Summarize
                  </Button>
                  <Button 
                    onClick={handleStartChat} 
                    disabled={!transcriptFile}
                    className="bg-cyan-600 text-white hover:bg-cyan-700 rounded-md"
                  >
                    Chat
                  </Button>
                </div>
              </div>
              {transcriptFile && (
                <p className="mt-2 text-sm text-gray-400">Current File: {transcriptFile.name}</p>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {summary && (
        <Card className="bg-gray-800 border-gray-700 rounded-lg overflow-hidden mt-6">
          <CardHeader className="bg-gray-750">
            <CardTitle className="text-cyan-400 font-work-sans font-normal">Summary of {activeTab === 'web' ? 'Web Page' : activeTab === 'youtube' ? 'YouTube Video' : 'Meeting Transcript'}</CardTitle>
          </CardHeader>
          <CardContent className="pt-6">
            <div className="p-3 bg-gray-700 text-gray-100 rounded-lg">
              <p>{formatMessageContent(summary)}</p>
            </div>
          </CardContent>
        </Card>
      )}

      {isChatVisible && (
        <Card className="bg-gray-800 border-gray-700 rounded-lg overflow-hidden mt-6">
          <CardHeader className="bg-gray-750">
            <CardTitle className="text-cyan-400 font-work-sans font-normal">Chat about {activeTab === 'web' ? 'Web Page' : activeTab === 'youtube' ? 'YouTube Video' : 'Meeting Transcript'}</CardTitle>
          </CardHeader>
          <CardContent className="pt-6">
            <ScrollArea className="h-[400px] w-full pr-4">
              {chatMessages.map((message, index) => 
                <div key={index} className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'} mb-4`}>
                  <div className={`flex items-end ${message.role === 'user' ? 'flex-row-reverse' : 'flex-row'}`}>
                    <Avatar className="w-8 h-8">
                      <AvatarFallback>{message.role === 'user' ? 'U' : 'AI'}</AvatarFallback>
                    </Avatar>
                    <div className={`mx-2 p-3 rounded-lg ${message.role === 'user' ? 'bg-cyan-600 text-white' : 'bg-gray-700 text-gray-100'}`}>
                      {formatMessageContent(message.content)}
                    </div>
                  </div>
                </div>
              )}
            </ScrollArea>
          </CardContent>
          <CardFooter className="bg-gray-750">
            <form onSubmit={handleAskQuestion} className="flex w-full items-center space-x-2">
              <Input 
                placeholder={`Ask a question about the ${activeTab === 'web' ? 'web page' : activeTab === 'youtube' ? 'YouTube video' : 'meeting transcript'}...`}
                value={question} 
                onChange={(e) => setQuestion(e.target.value)}
                className="flex-grow bg-gray-700 text-white border-gray-600 rounded-md"
              />
              <Button type="submit" disabled={isLoading || !question} className="bg-cyan-600 text-white hover:bg-cyan-700 rounded-md">
                {isLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                <span className="sr-only">Send</span>
              </Button>
            </form>
          </CardFooter>
        </Card>
      )}
    </div>
  )
}