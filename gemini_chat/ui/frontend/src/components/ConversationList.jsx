import React, { useState } from 'react';
import { 
  List, 
  ListItem, 
  ListItemText, 
  ListItemButton, 
  ListItemIcon,
  IconButton, 
  Button, 
  TextField, 
  Dialog, 
  DialogTitle, 
  DialogContent, 
  DialogActions,
  Menu,
  MenuItem,
  Typography,
  Box,
  Divider,
  CircularProgress
} from '@mui/material';
import { 
  Add as AddIcon, 
  MoreVert as MoreVertIcon, 
  Edit as EditIcon,
  Delete as DeleteIcon
} from '@mui/icons-material';
import { createConversation, renameConversation, deleteConversation } from '../services/api';

const ConversationList = ({ 
  conversations, 
  activeConversation, 
  onSelect, 
  onCreated, 
  onUpdated, 
  onDeleted 
}) => {
  // State for new conversation dialog
  const [newDialogOpen, setNewDialogOpen] = useState(false);
  const [newTitle, setNewTitle] = useState('');
  const [creating, setCreating] = useState(false);
  
  // State for edit conversation dialog
  const [editDialogOpen, setEditDialogOpen] = useState(false);
  const [editTitle, setEditTitle] = useState('');
  const [editingConversation, setEditingConversation] = useState(null);
  
  // State for delete confirmation dialog
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [deletingConversation, setDeletingConversation] = useState(null);
  
  // State for context menu
  const [contextMenu, setContextMenu] = useState(null);
  const [contextConversation, setContextConversation] = useState(null);
  
  // Handle creating a new conversation
  const handleCreateConversation = async () => {
    if (!newTitle.trim()) return;
    
    try {
      setCreating(true);
      const newConversation = await createConversation(newTitle);
      onCreated(newConversation);
      setNewDialogOpen(false);
      setNewTitle('');
    } catch (error) {
      console.error('Failed to create conversation:', error);
    } finally {
      setCreating(false);
    }
  };
  
  // Handle context menu
  const handleContextMenu = (event, conversation) => {
    event.preventDefault();
    event.stopPropagation();
    setContextMenu({ top: event.clientY, left: event.clientX });
    setContextConversation(conversation);
  };
  
  // Handle opening edit dialog
  const handleOpenEditDialog = (conversation) => {
    setContextMenu(null);
    setEditingConversation(conversation);
    setEditTitle(conversation.title);
    setEditDialogOpen(true);
  };
  
  // Handle renaming a conversation
  const handleRenameConversation = async () => {
    if (!editTitle.trim() || !editingConversation) return;
    
    try {
      const updated = await renameConversation(editingConversation.conversation_id, editTitle);
      onUpdated(updated);
      setEditDialogOpen(false);
      setEditingConversation(null);
      setEditTitle('');
    } catch (error) {
      console.error('Failed to rename conversation:', error);
    }
  };
  
  // Handle opening delete dialog
  const handleOpenDeleteDialog = (conversation) => {
    setContextMenu(null);
    setDeletingConversation(conversation);
    setDeleteDialogOpen(true);
  };
  
  // Handle deleting a conversation
  const handleDeleteConversation = async () => {
    if (!deletingConversation) return;
    
    try {
      await deleteConversation(deletingConversation.conversation_id);
      onDeleted(deletingConversation.conversation_id);
      setDeleteDialogOpen(false);
      setDeletingConversation(null);
    } catch (error) {
      console.error('Failed to delete conversation:', error);
    }
  };
  
  return (
    <Box sx={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      {/* New Conversation Button */}
      <Box sx={{ p: 2 }}>
        <Button 
          fullWidth 
          variant="contained" 
          startIcon={<AddIcon />}
          onClick={() => setNewDialogOpen(true)}
        >
          New Conversation
        </Button>
      </Box>
      
      <Divider />
      
      {/* Conversations List */}
      <List sx={{ overflow: 'auto', flexGrow: 1 }}>
        {conversations.length === 0 ? (
          <Box sx={{ p: 2, textAlign: 'center' }}>
            <Typography variant="body2" color="text.secondary">
              No conversations yet. Create one to get started.
            </Typography>
          </Box>
        ) : (
          conversations.map((conversation) => (
            <ListItem 
              key={conversation.conversation_id} 
              disablePadding
              secondaryAction={
                <IconButton 
                  edge="end" 
                  aria-label="options"
                  onClick={(e) => {
                    e.stopPropagation();
                    handleContextMenu(e, conversation);
                  }}
                >
                  <MoreVertIcon />
                </IconButton>
              }
            >
              <ListItemButton 
                selected={activeConversation?.conversation_id === conversation.conversation_id}
                onClick={() => onSelect(conversation)}
                onContextMenu={(e) => handleContextMenu(e, conversation)}
              >
                <ListItemText 
                  primary={conversation.title} 
                  secondary={`${conversation.message_count || 0} messages`}
                  primaryTypographyProps={{
                    noWrap: true,
                    style: { maxWidth: '180px' }
                  }}
                />
              </ListItemButton>
            </ListItem>
          ))
        )}
      </List>
      
      {/* New Conversation Dialog */}
      <Dialog open={newDialogOpen} onClose={() => setNewDialogOpen(false)}>
        <DialogTitle>New Conversation</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus
            margin="dense"
            label="Conversation Title"
            fullWidth
            value={newTitle}
            onChange={(e) => setNewTitle(e.target.value)}
            onKeyPress={(e) => {
              if (e.key === 'Enter') {
                handleCreateConversation();
              }
            }}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setNewDialogOpen(false)}>Cancel</Button>
          <Button 
            onClick={handleCreateConversation} 
            disabled={!newTitle.trim() || creating}
            startIcon={creating ? <CircularProgress size={16} /> : null}
          >
            Create
          </Button>
        </DialogActions>
      </Dialog>
      
      {/* Edit Conversation Dialog */}
      <Dialog open={editDialogOpen} onClose={() => setEditDialogOpen(false)}>
        <DialogTitle>Rename Conversation</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus
            margin="dense"
            label="Conversation Title"
            fullWidth
            value={editTitle}
            onChange={(e) => setEditTitle(e.target.value)}
            onKeyPress={(e) => {
              if (e.key === 'Enter') {
                handleRenameConversation();
              }
            }}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setEditDialogOpen(false)}>Cancel</Button>
          <Button 
            onClick={handleRenameConversation} 
            disabled={!editTitle.trim()}
          >
            Rename
          </Button>
        </DialogActions>
      </Dialog>
      
      {/* Delete Confirmation Dialog */}
      <Dialog open={deleteDialogOpen} onClose={() => setDeleteDialogOpen(false)}>
        <DialogTitle>Confirm Deletion</DialogTitle>
        <DialogContent>
          <Typography>
            Are you sure you want to delete the conversation "{deletingConversation?.title}"?
            This action cannot be undone.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleteDialogOpen(false)}>Cancel</Button>
          <Button 
            onClick={handleDeleteConversation} 
            color="error"
          >
            Delete
          </Button>
        </DialogActions>
      </Dialog>
      
      {/* Context Menu */}
      <Menu
        open={Boolean(contextMenu)}
        onClose={() => setContextMenu(null)}
        anchorReference="anchorPosition"
        anchorPosition={contextMenu || undefined}
      >
        <MenuItem onClick={() => handleOpenEditDialog(contextConversation)}>
          <ListItemIcon>
            <EditIcon fontSize="small" />
          </ListItemIcon>
          <ListItemText>Rename</ListItemText>
        </MenuItem>
        <MenuItem onClick={() => handleOpenDeleteDialog(contextConversation)}>
          <ListItemIcon>
            <DeleteIcon fontSize="small" />
          </ListItemIcon>
          <ListItemText>Delete</ListItemText>
        </MenuItem>
      </Menu>
    </Box>
  );
};

export default ConversationList;
