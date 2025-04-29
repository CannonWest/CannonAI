import { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { FiPlus, FiMessageSquare, FiSettings, FiTrash2 } from 'react-icons/fi';
import { format } from 'date-fns';
import useConversationStore, { Conversation } from '../store/useConversationStore';
import useSettingsStore from '../store/useSettingsStore';

interface SidebarProps {
  closeSidebar: () => void;
}

interface Conversation {
  id: number;
  title: string;
  updated_at: string;
}

const Sidebar = ({ closeSidebar }: SidebarProps) => {
  const navigate = useNavigate();
  const { 
    conversations, 
    isLoading, 
    fetchConversations, 
    createConversation, 
    deleteConversation 
  } = useConversationStore();
  const { settings } = useSettingsStore();

  // Fetch conversations on component mount
  useEffect(() => {
    fetchConversations();
  }, [fetchConversations]);

  // Create a new conversation
  const handleNewConversation = async () => {
    try {
      const newConversation = await createConversation(
        'New Conversation',
        settings.defaultProvider,
        settings.defaultModel
      );
      navigate(`/conversation/${newConversation.id}`);
      closeSidebar();
    } catch (error) {
      console.error('Failed to create conversation:', error);
    }
  };

  // Delete a conversation
  const handleDeleteConversation = async (id: number, e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    
    if (window.confirm('Are you sure you want to delete this conversation?')) {
      try {
        await deleteConversation(id);
      } catch (error) {
        console.error('Failed to delete conversation:', error);
      }
    }
  };

  return (
    <div className="flex flex-col h-full py-4">
      <div className="px-4 pb-4 border-b border-gray-200 dark:border-gray-700">
        <h2 className="text-xl font-semibold text-gray-800 dark:text-white">AI Chat Manager</h2>
      </div>
      
      <div className="px-4 py-4">
        <button
          onClick={handleNewConversation}
          className="w-full flex items-center justify-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors"
        >
          <FiPlus /> New Conversation
        </button>
      </div>
      
      <div className="flex-1 overflow-y-auto px-3">
        <h3 className="px-1 text-sm font-medium text-gray-500 dark:text-gray-400 mb-2">
          Recent Conversations
        </h3>
        
        {isLoading ? (
          <div className="text-center py-4 text-gray-500 dark:text-gray-400">Loading...</div>
        ) : conversations.length === 0 ? (
          <div className="text-center py-4 text-gray-500 dark:text-gray-400">
            No conversations yet
          </div>
        ) : (
          <ul className="space-y-1">
            {conversations.map(conv => (
              <li key={conv.id}>
                <Link
                  to={`/conversation/${conv.id}`}
                  onClick={closeSidebar}
                  className="flex items-center justify-between p-2 rounded-md hover:bg-gray-100 dark:hover:bg-gray-700"
                >
                  <div className="flex flex-col truncate">
                    <span className="text-sm font-medium truncate">{conv.title}</span>
                    <span className="text-xs text-gray-500">
                      {format(new Date(conv.updated_at), 'MMM d, yyyy')}
                    </span>
                  </div>
                  <button
                    onClick={(e) => handleDeleteConversation(conv.id, e)}
                    className="p-1 text-gray-500 hover:text-red-500"
                    aria-label="Delete conversation"
                  >
                    <FiTrash2 size={14} />
                  </button>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>
      
      <div className="px-3 py-3 mt-auto border-t border-gray-200 dark:border-gray-700">
        <Link
          to="/settings"
          onClick={closeSidebar}
          className="flex items-center gap-2 p-2 rounded-md hover:bg-gray-100 dark:hover:bg-gray-700"
        >
          <FiSettings />
          <span>Settings</span>
        </Link>
      </div>
    </div>
  );
};

export default Sidebar;
