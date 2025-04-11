import React, { useState, useEffect } from 'react';

const ConversationList = ({ 
  conversations, 
  currentConversationId, 
  onSelect, 
  onNew, 
  onDelete,
  onRename
}) => {
  const [editingId, setEditingId] = useState(null);
  const [newName, setNewName] = useState('');
  const [searchTerm, setSearchTerm] = useState('');
  const [showConfirmDelete, setShowConfirmDelete] = useState(null);
  
  // Filter conversations based on search term
  const filteredConversations = searchTerm
    ? conversations.filter(conv => 
        conv.name.toLowerCase().includes(searchTerm.toLowerCase()))
    : conversations;
  
  // Reset confirm delete when clicking elsewhere
  useEffect(() => {
    const handleClickOutside = (e) => {
      if (showConfirmDelete) {
        setShowConfirmDelete(null);
      }
    };
    
    document.addEventListener('click', handleClickOutside);
    return () => {
      document.removeEventListener('click', handleClickOutside);
    };
  }, [showConfirmDelete]);
  
  const handleDelete = (id, e) => {
    e.stopPropagation(); // Prevent triggering selection
    e.nativeEvent.stopImmediatePropagation(); // Prevent document click from clearing it immediately
    
    if (showConfirmDelete === id) {
      // Confirmed delete
      onDelete(id);
      setShowConfirmDelete(null);
    } else {
      // First click - show confirmation
      setShowConfirmDelete(id);
    }
  };
  
  const formatDate = (timestamp) => {
    if (!timestamp) return '';
    const date = new Date(timestamp);
    const now = new Date();
    
    // Same day - show time only
    if (date.toDateString() === now.toDateString()) {
      return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    }
    
    // This year - show month and day
    if (date.getFullYear() === now.getFullYear()) {
      return date.toLocaleDateString([], { month: 'short', day: 'numeric' });
    }
    
    // Different year - show date with year
    return date.toLocaleDateString([], { month: 'short', day: 'numeric', year: 'numeric' });
  };
  
  const handleEdit = (conv, e) => {
    e.stopPropagation(); // Prevent triggering selection
    setEditingId(conv.id);
    setNewName(conv.name);
  };
  
  const handleSaveEdit = (e) => {
    e.preventDefault();
    
    if (newName.trim() && editingId) {
      onRename(editingId, newName.trim());
      setEditingId(null);
      setNewName('');
    }
  };
  
  const handleKeyDown = (e) => {
    if (e.key === 'Escape') {
      setEditingId(null);
      setNewName('');
    }
  };
  
  return (
    <>
      <div className="cannon-conversations-header">
        <h2>Conversations</h2>
        <button 
          className="cannon-new-chat-btn" 
          onClick={() => onNew('New Conversation', 'You are a helpful assistant.')}
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <line x1="12" y1="5" x2="12" y2="19"></line>
            <line x1="5" y1="12" x2="19" y2="12"></line>
          </svg>
          New Chat
        </button>
      </div>
      
      <div className="cannon-search-box">
        <input
          type="text"
          placeholder="Search conversations..."
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
        />
        {searchTerm && (
          <button className="cannon-clear-search" onClick={() => setSearchTerm('')}>×</button>
        )}
      </div>
      
      <div className="cannon-conversations-list">
        {filteredConversations.length === 0 ? (
          <div className="cannon-no-conversations">
            {searchTerm ? "No conversations match your search" : "No conversations yet"}
          </div>
        ) : (
          <>
            {filteredConversations.map(conv => (
              <div 
                key={conv.id} 
                className={`cannon-conversation-item ${conv.id === currentConversationId ? 'active' : ''}`}
                onClick={() => onSelect(conv.id)}
              >
                {editingId === conv.id ? (
                  <form onSubmit={handleSaveEdit} className="cannon-rename-form">
                    <input
                      type="text"
                      value={newName}
                      onChange={(e) => setNewName(e.target.value)}
                      onKeyDown={handleKeyDown}
                      autoFocus
                    />
                    <button type="submit">Save</button>
                  </form>
                ) : (
                  <>
                    <div className="cannon-conversation-details">
                      <div className="cannon-conversation-name">{conv.name}</div>
                      <div className="cannon-conversation-time">
                        {formatDate(conv.modified_at || conv.created_at)}
                        {conv.message_count > 0 && (
                          <span className="cannon-message-count">
                            {conv.message_count} message{conv.message_count !== 1 ? 's' : ''}
                          </span>
                        )}
                      </div>
                    </div>
                    
                    <div className="cannon-conversation-actions">
                      <button 
                        className="cannon-edit-btn" 
                        onClick={(e) => handleEdit(conv, e)}
                        title="Rename"
                        aria-label="Rename conversation"
                      >
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <path d="M17 3a2.828 2.828 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z"></path>
                        </svg>
                      </button>
                      
                      <button 
                        className={`cannon-delete-btn ${showConfirmDelete === conv.id ? 'confirm' : ''}`}
                        onClick={(e) => handleDelete(conv.id, e)}
                        title={showConfirmDelete === conv.id ? "Click again to confirm" : "Delete"}
                        aria-label={showConfirmDelete === conv.id ? "Confirm delete" : "Delete conversation"}
                      >
                        {showConfirmDelete === conv.id ? (
                          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                            <polyline points="20 6 9 17 4 12"></polyline>
                          </svg>
                        ) : (
                          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                            <polyline points="3 6 5 6 21 6"></polyline>
                            <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                          </svg>
                        )}
                      </button>
                    </div>
                  </>
                )}
              </div>
            ))}
          </>
        )}
      </div>
    </>
  );
};

export default ConversationList;