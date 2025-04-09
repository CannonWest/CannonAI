import React, { useState } from 'react';
import { formatDate } from '../utils/formatters';

const ConversationList = ({ 
  conversations, 
  currentConversationId, 
  onSelect, 
  onNew, 
  onDelete,
  onRename
}) => {
  const [searchTerm, setSearchTerm] = useState('');
  const [showConfirmDelete, setShowConfirmDelete] = useState(null);
  const [editingId, setEditingId] = useState(null);
  const [newName, setNewName] = useState('');
  
  // Filter conversations based on search term
  const filteredConversations = conversations.filter(conv => 
    conv.name.toLowerCase().includes(searchTerm.toLowerCase())
  );
  
  const handleDelete = (id, e) => {
    e.stopPropagation(); // Prevent triggering selection
    
    if (showConfirmDelete === id) {
      // Confirmed - actually delete
      onDelete(id);
      setShowConfirmDelete(null);
    } else {
      // First click - show confirmation
      setShowConfirmDelete(id);
    }
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
