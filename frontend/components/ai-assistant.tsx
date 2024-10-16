"use client"

import React, { useState, useEffect, useRef } from 'react'
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle, CardFooter } from "@/components/ui/card"
import { Label } from "@/components/ui/label"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"
import { Globe, Loader2, Send, Youtube, FileText, Upload } from 'lucide-react'
import axios from 'axios'
import { v4 as uuidv4 } from 'uuid'
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
      const summaryContent = activeTab === 'transcript' 
      ? response.data.summary 
      : response.data.output;
      setSummary(cleanContent(summaryContent));
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
    <div className="min-h-screen bg-white text-black">
      <div className="max-w-full mx-auto p-4">
        <h1 className="text-4xl font-bold mb-8 text-center">What can I help you with?</h1>
        <Card className="w-full bg-white border border-gray-200 shadow-sm rounded-xl">
          <CardHeader>
            <CardTitle className="text-xl font-semibold">AI Assistant</CardTitle>
          </CardHeader>
          <CardContent>
            <Tabs value={activeTab} onValueChange={(value) => setActiveTab(value as 'web' | 'youtube' | 'transcript')} className="w-full">
              <TabsList className="grid w-full grid-cols-3 mb-6 rounded-lg">
                <TabsTrigger value="web" className="data-[state=active]:bg-gray-100 rounded-md">Web URL</TabsTrigger>
                <TabsTrigger value="youtube" className="data-[state=active]:bg-gray-100 rounded-md">YouTube</TabsTrigger>
                <TabsTrigger value="transcript" className="data-[state=active]:bg-gray-100 rounded-md">Meeting Transcript</TabsTrigger>
              </TabsList>
              <TabsContent value="web">
                <div className="space-y-4">
                  <Label htmlFor="url" className="text-sm font-medium text-gray-700">Web Page URL</Label>
                  <div className="flex space-x-2">
                    <Input 
                      id="url" 
                      placeholder="Enter URL" 
                      value={url} 
                      onChange={(e) => setUrl(e.target.value)} 
                      className="flex-grow rounded-md"
                    />
                    <Button 
                      onClick={handleSummarize} 
                      disabled={isLoading || !url} 
                      className="bg-black text-white hover:bg-gray-800 rounded-md"
                    >
                      {isLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Globe className="h-4 w-4 mr-2" />}
                      Summarize
                    </Button>
                    <Button 
                      onClick={handleStartChat} 
                      disabled={!url}
                      className="bg-black text-white hover:bg-gray-800 rounded-md"
                    >
                      Chat
                    </Button>
                  </div>
                </div>
              </TabsContent>
              <TabsContent value="youtube">
                <div className="space-y-4">
                  <Label htmlFor="youtubeUrl" className="text-sm font-medium text-gray-700">YouTube Video URL</Label>
                  <div className="flex space-x-2">
                    <Input 
                      id="youtubeUrl" 
                      placeholder="Enter YouTube URL" 
                      value={youtubeUrl} 
                      onChange={(e) => setYoutubeUrl(e.target.value)} 
                      className="flex-grow rounded-md"
                    />
                    <Button 
                      onClick={handleSummarize} 
                      disabled={isLoading || !youtubeUrl} 
                      className="bg-black text-white hover:bg-gray-800 rounded-md"
                    >
                      {isLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Youtube className="h-4 w-4 mr-2" />}
                      Summarize
                    </Button>
                    <Button 
                      onClick={handleStartChat} 
                      disabled={!youtubeUrl}
                      className="bg-black text-white hover:bg-gray-800 rounded-md"
                    >
                      Chat
                    </Button>
                  </div>
                </div>
              </TabsContent>
              <TabsContent value="transcript">
                <div className="space-y-4">
                  <Label htmlFor="transcriptFile" className="text-sm font-medium text-gray-700">Upload Transcript File</Label>
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
                      className="bg-gray-100 text-gray-700 hover:bg-gray-200 flex-grow justify-start rounded-md"
                    >
                      <Upload className="h-4 w-4 mr-2" />
                      {transcriptFile ? transcriptFile.name : "Choose file"}
                    </Button>
                    <Button 
                      onClick={handleSummarize} 
                      disabled={isLoading || !transcriptFile} 
                      className="bg-black text-white hover:bg-gray-800 rounded-md"
                    >
                      {isLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileText className="h-4 w-4 mr-2" />}
                      Summarize
                    </Button>
                    <Button 
                      onClick={handleStartChat} 
                      disabled={!transcriptFile}
                      className="bg-black text-white hover:bg-gray-800 rounded-md"
                    >
                      Chat
                    </Button>
                  </div>
                </div>
              </TabsContent>
            </Tabs>
          </CardContent>
        </Card>

        {summary && (
          <Card className="mt-8 w-full rounded-xl">
            <CardHeader>
              <CardTitle className="text-xl font-semibold">Summary of {activeTab === 'web' ? 'Web Page' : activeTab === 'youtube' ? 'YouTube Video' : 'Meeting Transcript'}</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-gray-700">{formatMessageContent(summary)}</p>
            </CardContent>
          </Card>
        )}

        {isChatVisible && (
          <Card className="mt-8 w-full rounded-xl">
            <CardHeader>
              <CardTitle className="text-xl font-semibold">Chat about {activeTab === 'web' ? 'Web Page' : activeTab === 'youtube' ? 'YouTube Video' : 'Meeting Transcript'}</CardTitle>
            </CardHeader>
            <CardContent>
              <ScrollArea className="h-[400px] w-full pr-4">
                {chatMessages.map((message, index) => 
                  <div key={index} className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'} mb-4`}>
                    <div className={`flex items-end ${message.role === 'user' ? 'flex-row-reverse' : 'flex-row'}`}>
                      <Avatar className="w-8 h-8">
                        <AvatarFallback>{message.role === 'user' ? 'U' : 'AI'}</AvatarFallback>
                      </Avatar>
                      <div className={`mx-2 p-3 rounded-lg ${message.role === 'user' ? 'bg-gray-100' : 'bg-black text-white'}`}>
                        {formatMessageContent(message.content)}
                      </div>
                    </div>
                  </div>
                )}
              </ScrollArea>
            </CardContent>
            <CardFooter>
              <form onSubmit={handleAskQuestion} className="flex w-full items-center space-x-2">
                <Input 
                  placeholder={`Ask a question about the ${activeTab === 'web' ? 'web page' : activeTab === 'youtube' ? 'YouTube video' : 'meeting transcript'}...`}
                  value={question} 
                  onChange={(e) => setQuestion(e.target.value)}
                  className="flex-grow rounded-md"
                />
                <Button type="submit" disabled={isLoading || !question} className="bg-black text-white hover:bg-gray-800 rounded-md">
                  {isLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                  <span className="sr-only">Send</span>
                </Button>
              </form>
            </CardFooter>
          </Card>
        )}
      </div>
    </div>
  )
}