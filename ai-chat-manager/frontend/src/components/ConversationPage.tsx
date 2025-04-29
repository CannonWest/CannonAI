import { useState, useEffect, useRef, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { getDefaultConversation } from '../services/api';
import { FiSend, FiSettings } from 'react-icons/fi';
import ReactMarkdown from 'react-markdown';
import useWebSocket from '../hooks/useWebSocket';

interface Message {
  id: number | string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  created_at: string;
}

interface ModelSettings {
  model_provider: string;
  model_name: string;
  temperature: number;
  max_tokens?: number;
}

const ConversationPage = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputMessage, setInputMessage] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [settings, setSettings] = useState<ModelSettings>({
    model_provider: 'openai',
    model_name: 'gpt-3.5-turbo',
    temperature: 0.7
  });
  const [showSettings, setShowSettings] = useState(false);
  
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // WebSocket for streaming chat
  // Construct proper WebSocket URL based on current protocol (ws or wss)
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = id ? `${protocol}//${window.location.host}/api/v1/conversations/${id}/stream` : null;
  const {
    isConnected,
    sendMessage: sendWSMessage,
    error: wsError
  } = useWebSocket(
    wsUrl,
    {
      autoConnect: !!wsUrl,
      onMessage: (data) => {
        if (data.type === 'chunk' && data.content) {
          // Handle streaming chunks
          setMessages(prev => {
            const lastMessage = prev[prev.length - 1];
            
            // If the last message is from the assistant and is streaming,
            // update it with the new chunk
            if (lastMessage?.role === 'assistant' && lastMessage.id === 'streaming') {
              const updatedMessages = [...prev.slice(0, -1)];
              updatedMessages.push({
                ...lastMessage,
                content: lastMessage.content + data.content
              });
              return updatedMessages;
            }
            
            // Otherwise, create a new streaming message
            return [...prev, {
              id: 'streaming',
              role: 'assistant',
              content: data.content,
              created_at: new Date().toISOString()
            }];
          });
        } else if (data.type === 'done') {
          // Finalize the streaming message
          setMessages(prev => {
            const lastIndex = prev.findIndex(msg => msg.id === 'streaming');
            if (lastIndex >= 0) {
              const updatedMessages = [...prev];
              updatedMessages[lastIndex] = {
                ...updatedMessages[lastIndex],
                id: Date.now()
              };
              return updatedMessages;
            }
            return prev;
          });
          setIsLoading(false);
        } else if (data.type === 'error') {
          console.error('WebSocket error:', data.error);
          setIsLoading(false);
        }
      }
    }
  );

  // Scroll to bottom of messages
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  // Fetch conversation and messages
  useEffect(() => {
    const fetchConversation = async () => {
      // For 'new' or no ID, get the default conversation
      if (id === 'new' || !id) {
        try {
          const defaultConversation = await getDefaultConversation();
          // Redirect to the default conversation
          navigate(`/conversation/${defaultConversation.id}`, { replace: true });
          return;
        } catch (error) {
          console.error('Failed to fetch default conversation:', error);
          return;
        }
      }
      
      try {
        // First try to get the conversation
        let conversationData;
        try {
          const response = await fetch(`/api/v1/conversations/${id}`);
          if (!response.ok && response.status === 404) {
            // If 404, try to get the default conversation
            console.log('Conversation not found, getting default');
            const defaultConversation = await getDefaultConversation();
            navigate(`/conversation/${defaultConversation.id}`, { replace: true });
            return;
          }
          conversationData = await response.json();
        } catch (error) {
          console.error('Error fetching conversation, trying default:', error);
          const defaultConversation = await getDefaultConversation();
          navigate(`/conversation/${defaultConversation.id}`, { replace: true });
          return;
        }
        
        // Now get the messages
        const apiMessagesData = await fetch(`/api/v1/conversations/${id}/messages`).then(res => res.json());
        
        if (apiMessagesData && apiMessagesData.length > 0) {
          setMessages(apiMessagesData);
        } else {
          // Fallback placeholder data if API returns empty messages
          const placeholderMessages: Message[] = [
          {
            id: 1,
            role: 'system',
            content: 'You are chatting with an AI assistant.',
            created_at: new Date().toISOString()
          },
          {
            id: 2,
            role: 'user',
            content: 'Hello! How can you help me today?',
            created_at: new Date().toISOString()
          },
          {
            id: 3,
            role: 'assistant',
            content: 'Hi there! I\'m your AI assistant. I can help you with information, creative writing, problem-solving, and more. Just let me know what you need assistance with!',
            created_at: new Date().toISOString()
          }
        ];
        
          setMessages(placeholderMessages);
        }
        
        setSettings({
            model_provider: conversationData.model_provider,
            model_name: conversationData.model_name,
            temperature: conversationData.settings?.temperature || 0.7,
            max_tokens: conversationData.settings?.max_tokens
          });
      
      } catch (error) {
        console.error('Failed to fetch conversation:', error);
      }
    };

    fetchConversation();
  }, [id]);

  // Scroll to bottom when messages change
  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  // Auto-resize textarea
  useEffect(() => {
    const textarea = textareaRef.current;
    if (textarea) {
      textarea.style.height = 'auto';
      textarea.style.height = `${textarea.scrollHeight}px`;
    }
  }, [inputMessage]);

  // Handle send message via WebSocket
  const handleSendMessage = async () => {
    if (!inputMessage.trim() || isLoading) return;
    
    const newUserMessage: Message = {
      id: Date.now(),
      role: 'user',
      content: inputMessage,
      created_at: new Date().toISOString()
    };
    
    setMessages([...messages, newUserMessage]);
    setInputMessage('');
    setIsLoading(true);
    
    if (isConnected) {
      // Send via WebSocket
      sendWSMessage({
        type: 'message',
        content: inputMessage
      });
    } else {
      // Fallback to REST API
      try {
        // TODO: Implement actual API call
        // const response = await sendMessage(id, inputMessage);
        
        // Placeholder until API is connected
        // Simulate API delay
        await new Promise(resolve => setTimeout(resolve, 1000));
        
        const aiResponse: Message = {
          id: Date.now() + 1,
          role: 'assistant',
          content: 'This is a placeholder response. WebSocket connection failed. The actual API integration is pending.',
          created_at: new Date().toISOString()
        };
        
        setMessages(prev => [...prev, aiResponse]);
      } catch (error) {
        console.error('Failed to send message:', error);
      } finally {
        setIsLoading(false);
      }
    }
  };

  // Handle key press (submit on Enter, new line on Shift+Enter)
  const handleKeyPress = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  // Update settings
  const handleSettingsChange = (settingName: string, value: string | number) => {
    setSettings(prev => ({
      ...prev,
      [settingName]: value
    }));
  };

  return (
    <div className="flex flex-col h-full">
      {/* Conversation header */}
      <div className="flex justify-between items-center px-4 py-3 bg-white dark:bg-gray-800 shadow-sm rounded-t-lg">
        <h2 className="text-xl font-semibold text-gray-800 dark:text-white">
          {id === 'new' ? 'New Conversation' : `Conversation #${id}`}
        </h2>
        <div className="flex items-center space-x-2">
          {wsError && (
            <span className="text-xs text-red-500">WebSocket error</span>
          )}
          <button
            onClick={() => setShowSettings(!showSettings)}
            className="p-2 rounded-full hover:bg-gray-100 dark:hover:bg-gray-700"
            aria-label="Settings"
          >
            <FiSettings className="h-5 w-5 text-gray-600 dark:text-gray-300" />
          </button>
        </div>
      </div>
      
      {/* Settings panel */}
      {showSettings && (
        <div className="p-4 bg-gray-50 dark:bg-gray-700 border-b border-gray-200 dark:border-gray-600">
          <h3 className="font-medium mb-3 text-gray-800 dark:text-white">Model Settings</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Provider
              </label>
              <select
                value={settings.model_provider}
                onChange={(e) => handleSettingsChange('model_provider', e.target.value)}
                className="w-full p-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-gray-800 dark:text-white"
              >
                <option value="openai">OpenAI</option>
                <option value="google">Google</option>
                <option value="anthropic">Anthropic</option>
              </select>
            </div>
            
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Model
              </label>
              <select
                value={settings.model_name}
                onChange={(e) => handleSettingsChange('model_name', e.target.value)}
                className="w-full p-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-gray-800 dark:text-white"
              >
                {settings.model_provider === 'openai' && (
                  <>
                    <option value="gpt-4">GPT-4</option>
                    <option value="gpt-3.5-turbo">GPT-3.5 Turbo</option>
                    <option value="gpt-4-turbo">GPT-4 Turbo</option>
                  </>
                )}
                {settings.model_provider === 'google' && (
                  <>
                    <option value="gemini-pro">Gemini Pro</option>
                    <option value="gemini-ultra">Gemini Ultra</option>
                  </>
                )}
                {settings.model_provider === 'anthropic' && (
                  <>
                    <option value="claude-3-opus">Claude 3 Opus</option>
                    <option value="claude-3-sonnet">Claude 3 Sonnet</option>
                    <option value="claude-3-haiku">Claude 3 Haiku</option>
                  </>
                )}
              </select>
            </div>
            
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Temperature: {settings.temperature}
              </label>
              <input
                type="range"
                min="0"
                max="2"
                step="0.1"
                value={settings.temperature}
                onChange={(e) => handleSettingsChange('temperature', parseFloat(e.target.value))}
                className="w-full"
              />
            </div>
            
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Max Tokens
              </label>
              <input
                type="number"
                value={settings.max_tokens || ''}
                onChange={(e) => handleSettingsChange('max_tokens', parseInt(e.target.value) || undefined)}
                placeholder="Optional"
                className="w-full p-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-gray-800 dark:text-white"
              />
            </div>
          </div>
          
          <div className="mt-4 flex justify-end">
            <button
              onClick={() => setShowSettings(false)}
              className="px-4 py-2 bg-blue-600 text-white font-medium rounded-md hover:bg-blue-700"
            >
              Apply
            </button>
          </div>
        </div>
      )}
      
      {/* Messages container */}
      <div className="flex-1 overflow-y-auto p-4 bg-gray-50 dark:bg-gray-800">
        {messages.length === 0 ? (
          <div className="flex items-center justify-center h-full text-gray-500 dark:text-gray-400">
            Start a conversation...
          </div>
        ) : (
          <div className="space-y-4">
            {messages.map(message => (
              <div 
                key={message.id}
                className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
              >
                <div 
                  className={`max-w-3xl rounded-lg px-4 py-2 ${
                    message.role === 'user' 
                      ? 'bg-blue-600 text-white' 
                      : message.role === 'system'
                        ? 'bg-gray-300 dark:bg-gray-600 text-gray-800 dark:text-white'
                        : 'bg-white dark:bg-gray-700 text-gray-800 dark:text-white border border-gray-200 dark:border-gray-600'
                  }`}
                >
                  <ReactMarkdown className="prose dark:prose-invert">
                    {message.content}
                  </ReactMarkdown>
                </div>
              </div>
            ))}
            {isLoading && !messages.some(m => m.id === 'streaming') && (
              <div className="flex justify-start">
                <div className="max-w-3xl rounded-lg px-4 py-2 bg-white dark:bg-gray-700 text-gray-800 dark:text-white border border-gray-200 dark:border-gray-600">
                  <div className="flex space-x-2">
                    <div className="h-2 w-2 bg-gray-400 rounded-full animate-bounce"></div>
                    <div className="h-2 w-2 bg-gray-400 rounded-full animate-bounce delay-100"></div>
                    <div className="h-2 w-2 bg-gray-400 rounded-full animate-bounce delay-200"></div>
                  </div>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>
        )}
      </div>
      
      {/* Input container */}
      <div className="p-4 bg-white dark:bg-gray-800 border-t border-gray-200 dark:border-gray-700 rounded-b-lg">
        <div className="flex items-end space-x-2">
          <div className="flex-1 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 p-2">
            <textarea
              ref={textareaRef}
              value={inputMessage}
              onChange={(e) => setInputMessage(e.target.value)}
              onKeyDown={handleKeyPress}
              placeholder="Type a message..."
              className="w-full bg-transparent resize-none border-0 focus:ring-0 text-gray-800 dark:text-white focus:outline-none max-h-32"
              rows={1}
            ></textarea>
          </div>
          <button
            onClick={handleSendMessage}
            disabled={isLoading || !inputMessage.trim()}
            className={`p-3 rounded-full ${
              isLoading || !inputMessage.trim()
                ? 'bg-gray-300 dark:bg-gray-600 text-gray-500 dark:text-gray-400 cursor-not-allowed'
                : 'bg-blue-600 text-white hover:bg-blue-700'
            }`}
          >
            <FiSend className="h-5 w-5" />
          </button>
        </div>
        <div className="text-xs text-gray-500 dark:text-gray-400 mt-2 text-right">
          Press Enter to send, Shift+Enter for new line
        </div>
      </div>
    </div>
  );
};

export default ConversationPage;
