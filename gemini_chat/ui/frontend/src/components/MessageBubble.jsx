import React from 'react';
import { Paper, Box, Typography, CircularProgress } from '@mui/material';
import ReactMarkdown from 'react-markdown';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { atomDark } from 'react-syntax-highlighter/dist/esm/styles/prism';

// Highlighted code block component for markdown
const CodeBlock = ({ node, inline, className, children, ...props }) => {
  const match = /language-(\w+)/.exec(className || '');
  const language = match ? match[1] : 'text';
  
  return !inline ? (
    <SyntaxHighlighter
      style={atomDark}
      language={language}
      PreTag="div"
      {...props}
    >
      {String(children).replace(/\n$/, '')}
    </SyntaxHighlighter>
  ) : (
    <code className={className} {...props}>
      {children}
    </code>
  );
};

const MessageBubble = ({ message, isUser, isStreaming = false }) => {
  // Style based on user or AI message
  const userStyle = {
    bgcolor: 'primary.main',
    color: 'white',
    ml: 'auto',
    mr: 1,
    maxWidth: '70%',
  };
  
  const aiStyle = {
    bgcolor: 'background.paper',
    color: 'text.primary',
    border: 1,
    borderColor: 'divider',
    ml: 1,
    mr: 'auto',
    maxWidth: '80%',
  };
  
  const bubbleStyle = isUser ? userStyle : aiStyle;
  
  return (
    <Box
      sx={{
        display: 'flex',
        mb: 2,
        position: 'relative',
      }}
    >
      <Paper
        elevation={1}
        sx={{
          p: 2,
          borderRadius: 3,
          ...bubbleStyle,
        }}
      >
        {isUser ? (
          // User messages are simple text
          <Typography variant="body1">{message}</Typography>
        ) : (
          // AI messages render markdown with code highlighting
          <Box sx={{ 
            '& pre': { 
              borderRadius: 1,
              overflow: 'auto',
              maxWidth: '100%',
            },
            '& code': {
              padding: '0.2em 0.4em',
              margin: 0,
              borderRadius: 1,
              backgroundColor: 'rgba(0, 0, 0, 0.1)',
              fontFamily: 'monospace',
            },
            '& blockquote': {
              borderLeft: '4px solid',
              borderColor: 'divider',
              pl: 2,
              color: 'text.secondary',
            },
            '& a': {
              color: 'primary.main',
              textDecoration: 'none',
              '&:hover': {
                textDecoration: 'underline',
              },
            },
            '& p': {
              my: 1,
            },
            '& ul, & ol': {
              pl: 3,
            },
            '& table': {
              borderCollapse: 'collapse',
              width: '100%',
            },
            '& th, & td': {
              border: '1px solid',
              borderColor: 'divider',
              p: 1,
            }
          }}>
            <ReactMarkdown
              components={{
                code: CodeBlock,
              }}
            >
              {message}
            </ReactMarkdown>
          </Box>
        )}
        
        {/* Show loading indicator for streaming messages */}
        {isStreaming && (
          <Box sx={{ display: 'flex', justifyContent: 'center', mt: 1 }}>
            <CircularProgress size={16} />
          </Box>
        )}
      </Paper>
    </Box>
  );
};

export default MessageBubble;
