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
    const handleClickOutside = () => {
      setShowConfirmDelete(null);
    };
    
    document.addEventListener('click', handleClickOutside);
    return () => {
      document.removeEventListener('click', handleClickOutside);
    };
  }, []);
  
  const handleDelete = (id, e) => {
    e.stopPropagation(); // Prevent triggering selection
    
    if (showConfirmDelete === id) {
      // Confirmed delete
      onDelete(id);
      setShowConfirmDelete(null);
    } else {
      // First click - show confirmation
      setShowConfirmDelete(id);
      e.nativeEvent.stopImmediatePropagation(); // Prevent document click from clearing it immediately
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
    <div className="conversation-list">
      <div className="list-header">
        <h2>Conversations</h2>
        <button className="new-conversation-btn" onClick={onNew}>
          + New Chat
        </button>
      </div>
      
      <div className="search-box">
        <input
          type="text"
          placeholder="Search conversations..."
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
        />
        {searchTerm && (
          <button className="clear-search" onClick={() => setSearchTerm('')}>×</button>
        )}
      </div>
      
      <ul className="conversations">
        {filteredConversations.length === 0 ? (
          <li className="no-conversations">
            {searchTerm ? "No conversations match your search" : "No conversations yet"}
          </li>
        ) : (
          filteredConversations.map(conv => (
            <li 
              key={conv.id} 
              className={`conversation-item ${conv.id === currentConversationId ? 'active' : ''}`}
              onClick={() => onSelect(conv.id)}
            >
              {editingId === conv.id ? (
                <form onSubmit={handleSaveEdit} className="rename-form">
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
                  <div className="conversation-details">
                    <span className="conversation-name">{conv.name}</span>
                    <span className="conversation-date">
                      {formatDate(conv.modified_at || conv.created_at)}
                    </span>
                  </div>
                  
                  <div className="conversation-actions">
                    <button 
                      className="edit-btn" 
                      onClick={(e) => handleEdit(conv, e)}
                      title="Rename"
                    >
                      ✎
                    </button>
                    
                    <button 
                      className={`delete-btn ${showConfirmDelete === conv.id ? 'confirm' : ''}`}
                      onClick={(e) => handleDelete(conv.id, e)}
                      title={showConfirmDelete === conv.id ? "Click again to confirm" : "Delete"}
                    >
                      {showConfirmDelete === conv.id ? '✓' : '×'}
                    </button>
                  </div>
                </>
              )}
            </li>
          ))
        )}
      </ul>
      
      {showConfirmDelete && (
        <div className="click-away" onClick={() => setShowConfirmDelete(null)}></div>
      )}
    </div>
  );
};

export default ConversationList;
