import React, { useState, useEffect } from 'react';
import { Routes, Route } from 'react-router-dom';
import { Box, CssBaseline, Drawer, AppBar, Toolbar, Typography, Divider, IconButton, useTheme, useMediaQuery } from '@mui/material';
import { Menu as MenuIcon, DarkMode, LightMode } from '@mui/icons-material';
import { ThemeProvider, createTheme } from '@mui/material/styles';

// Import components
import ChatView from './components/ChatView';
import ConversationList from './components/ConversationList';
import SettingsPanel from './components/SettingsPanel';

// Import services
import { getConfig, listConversations } from './services/api';

// Drawer width for desktop
const drawerWidth = 280;

function App() {
  const theme = useTheme();
  const prefersDarkMode = useMediaQuery('(prefers-color-scheme: dark)');
  const isMobile = useMediaQuery(theme.breakpoints.down('md'));
  
  // State management
  const [darkMode, setDarkMode] = useState(prefersDarkMode);
  const [drawerOpen, setDrawerOpen] = useState(!isMobile);
  const [conversations, setConversations] = useState([]);
  const [activeConversation, setActiveConversation] = useState(null);
  const [config, setConfig] = useState({
    api_key_set: false,
    default_model: '',
    generation_params: {}
  });
  const [clientId] = useState(() => {
    // Generate or retrieve client ID for session management
    const storedId = localStorage.getItem('clientId');
    if (storedId) return storedId;
    
    const newId = Math.random().toString(36).substring(2, 15);
    localStorage.setItem('clientId', newId);
    return newId;
  });

  // Create custom theme based on dark mode preference
  const customTheme = React.useMemo(
    () =>
      createTheme({
        palette: {
          mode: darkMode ? 'dark' : 'light',
          primary: {
            main: darkMode ? '#90caf9' : '#1976d2',
          },
          secondary: {
            main: darkMode ? '#ce93d8' : '#9c27b0',
          },
          background: {
            default: darkMode ? '#121212' : '#f5f5f5',
            paper: darkMode ? '#1e1e1e' : '#ffffff',
          },
        },
      }),
    [darkMode],
  );

  // Load initial data
  useEffect(() => {
    // Fetch configuration
    const loadConfig = async () => {
      try {
        const configData = await getConfig();
        setConfig(configData);
      } catch (error) {
        console.error('Failed to load configuration:', error);
      }
    };

    // Fetch conversations
    const loadConversations = async () => {
      try {
        const conversationsData = await listConversations();
        setConversations(conversationsData);
        
        // Set active conversation from localStorage or use the first one
        const storedConversationId = localStorage.getItem('activeConversationId');
        
        if (storedConversationId && conversationsData.some(c => c.conversation_id === storedConversationId)) {
          setActiveConversation(conversationsData.find(c => c.conversation_id === storedConversationId));
        } else if (conversationsData.length > 0) {
          setActiveConversation(conversationsData[0]);
          localStorage.setItem('activeConversationId', conversationsData[0].conversation_id);
        }
      } catch (error) {
        console.error('Failed to load conversations:', error);
      }
    };

    loadConfig();
    loadConversations();
  }, []);

  // Handle conversation selection
  const handleConversationSelect = (conversation) => {
    setActiveConversation(conversation);
    localStorage.setItem('activeConversationId', conversation.conversation_id);
    
    // Close drawer on mobile after selection
    if (isMobile) {
      setDrawerOpen(false);
    }
  };

  // Handle new conversation creation
  const handleConversationCreated = (newConversation) => {
    setConversations(prev => [newConversation, ...prev]);
    setActiveConversation(newConversation);
    localStorage.setItem('activeConversationId', newConversation.conversation_id);
  };

  // Handle conversation update (e.g., rename)
  const handleConversationUpdated = (updatedConversation) => {
    setConversations(prev => 
      prev.map(conv => 
        conv.conversation_id === updatedConversation.conversation_id 
          ? { ...conv, ...updatedConversation } 
          : conv
      )
    );
    
    if (activeConversation && activeConversation.conversation_id === updatedConversation.conversation_id) {
      setActiveConversation(prev => ({ ...prev, ...updatedConversation }));
    }
  };

  // Handle conversation deletion
  const handleConversationDeleted = (conversationId) => {
    setConversations(prev => prev.filter(conv => conv.conversation_id !== conversationId));
    
    // If active conversation was deleted, select another one
    if (activeConversation && activeConversation.conversation_id === conversationId) {
      const remainingConversations = conversations.filter(conv => conv.conversation_id !== conversationId);
      
      if (remainingConversations.length > 0) {
        setActiveConversation(remainingConversations[0]);
        localStorage.setItem('activeConversationId', remainingConversations[0].conversation_id);
      } else {
        setActiveConversation(null);
        localStorage.removeItem('activeConversationId');
      }
    }
  };

  // Toggle dark mode
  const toggleDarkMode = () => {
    setDarkMode(!darkMode);
    localStorage.setItem('darkMode', !darkMode ? 'true' : 'false');
  };

  // Toggle drawer
  const toggleDrawer = () => {
    setDrawerOpen(!drawerOpen);
  };

  // Create the drawer content
  const drawerContent = (
    <>
      <Toolbar sx={{ justifyContent: 'space-between' }}>
        <Typography variant="h6" noWrap component="div">
          Conversations
        </Typography>
      </Toolbar>
      <Divider />
      <ConversationList 
        conversations={conversations}
        activeConversation={activeConversation}
        onSelect={handleConversationSelect}
        onCreated={handleConversationCreated}
        onUpdated={handleConversationUpdated}
        onDeleted={handleConversationDeleted}
      />
    </>
  );

  return (
    <ThemeProvider theme={customTheme}>
      <Box sx={{ display: 'flex', height: '100vh' }}>
        <CssBaseline />
        
        {/* App Bar */}
        <AppBar
          position="fixed"
          sx={{
            width: { md: drawerOpen ? `calc(100% - ${drawerWidth}px)` : '100%' },
            ml: { md: drawerOpen ? `${drawerWidth}px` : 0 },
            zIndex: (theme) => theme.zIndex.drawer + 1,
          }}
        >
          <Toolbar>
            <IconButton
              color="inherit"
              aria-label="open drawer"
              edge="start"
              onClick={toggleDrawer}
              sx={{ mr: 2, display: { md: 'none' } }}
            >
              <MenuIcon />
            </IconButton>
            
            <Typography variant="h6" noWrap component="div" sx={{ flexGrow: 1 }}>
              Gemini Chat {activeConversation && `- ${activeConversation.title}`}
            </Typography>
            
            <IconButton color="inherit" onClick={toggleDarkMode}>
              {darkMode ? <LightMode /> : <DarkMode />}
            </IconButton>
          </Toolbar>
        </AppBar>
        
        {/* Side Drawer */}
        <Drawer
          variant={isMobile ? "temporary" : "persistent"}
          open={drawerOpen}
          onClose={toggleDrawer}
          sx={{
            width: drawerWidth,
            flexShrink: 0,
            '& .MuiDrawer-paper': {
              width: drawerWidth,
              boxSizing: 'border-box',
            },
          }}
        >
          {drawerContent}
        </Drawer>
        
        {/* Main Content */}
        <Box
          component="main"
          sx={{
            flexGrow: 1,
            p: 3,
            width: { md: drawerOpen ? `calc(100% - ${drawerWidth}px)` : '100%' },
            height: '100vh',
            overflow: 'hidden',
            display: 'flex',
            flexDirection: 'column',
          }}
        >
          <Toolbar /> {/* Spacer for app bar */}
          
          <Routes>
            <Route 
              path="/" 
              element={
                <ChatView 
                  activeConversation={activeConversation}
                  config={config}
                  clientId={clientId}
                  onConversationUpdated={handleConversationUpdated}
                />
              } 
            />
            <Route 
              path="/settings" 
              element={
                <SettingsPanel 
                  config={config}
                  setConfig={setConfig}
                />
              } 
            />
          </Routes>
        </Box>
      </Box>
    </ThemeProvider>
  );
}

export default App;
