// Utility functions for formatting data

// Format date strings
export const formatDate = (dateString) => {
  if (!dateString) return '';
  
  try {
    const date = new Date(dateString);
    
    // Check if date is valid
    if (isNaN(date.getTime())) return dateString;
    
    // Format: "Mar 15, 2023, 2:30 PM"
    return new Intl.DateTimeFormat('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: 'numeric',
      minute: 'numeric',
      hour12: true
    }).format(date);
  } catch (error) {
    console.error("Error formatting date:", error);
    return dateString;
  }
};

// Format token usage for display
export const formatTokenUsage = (usage) => {
  if (!usage) return 'No token usage data';
  
  const promptTokens = usage.prompt_tokens || 0;
  const completionTokens = usage.completion_tokens || 0;
  const totalTokens = usage.total_tokens || (promptTokens + completionTokens);
  
  // Calculate approximate cost (very rough estimate)
  // These rates are approximate and will vary by model
  const PROMPT_RATE = 0.00001; // $0.01 per 1000 tokens
  const COMPLETION_RATE = 0.00003; // $0.03 per 1000 tokens
  
  const estimatedCost = (
    (promptTokens * PROMPT_RATE) + 
    (completionTokens * COMPLETION_RATE)
  ).toFixed(4);
  
  return `Input: ${promptTokens.toLocaleString()} · Output: ${completionTokens.toLocaleString()} · Total: ${totalTokens.toLocaleString()} tokens · Est. cost: $${estimatedCost}`;
};

// Simple detection for code blocks
const detectLanguage = (codeBlock) => {
  // Extract language from code fence if present
  const match = codeBlock.match(/```([a-zA-Z0-9_+-]+)?/);
  return match && match[1] ? match[1].toLowerCase() : '';
};

// Format message content (handle markdown, code blocks, etc.)
export const formatMessageContent = (content) => {
  if (!content) return '';
  
  // This is a simplified formatter that should be replaced with
  // React components using react-markdown and syntax highlighting
  // For now, we'll just add some basic HTML formatting
  
  const formatted = content
    // Replace code blocks with HTML
    .replace(/```([\s\S]*?)```/g, (match, code) => {
      const language = detectLanguage(match);
      return `<pre class="code-block ${language}"><code>${code.replace(/```[a-zA-Z0-9_+-]*\n?/, '')}</code></pre>`;
    })
    // Replace inline code with HTML
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    // Replace headers
    .replace(/^### (.*$)/gim, '<h3>$1</h3>')
    .replace(/^## (.*$)/gim, '<h2>$1</h2>')
    .replace(/^# (.*$)/gim, '<h1>$1</h1>')
    // Replace bold and italic text
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.*?)\*/g, '<em>$1</em>')
    // Replace paragraphs
    .replace(/\n\n/g, '<br><br>');
  
  return formatted;
};

// Format error messages
export const formatError = (error) => {
  if (!error) return 'An unknown error occurred';
  
  // Handle various error types
  if (typeof error === 'string') return error;
  
  if (error.response) {
    // API error with response
    const status = error.response.status;
    const data = error.response.data || {};
    
    // Format based on common API error patterns
    if (status === 401) {
      return 'Authentication failed. Please check your API key.';
    } else if (status === 429) {
      return 'Rate limit exceeded. Please try again later.';
    } else if (status >= 500) {
      return `Server error (${status}). The AI service may be experiencing issues.`;
    }
    
    // Use error message from response if available
    return data.error?.message || data.message || `Error ${status}: ${JSON.stringify(data)}`;
  }
  
  // Network errors
  if (error.request) {
    return 'Network error. Please check your internet connection.';
  }
  
  // Default to error message or toString
  return error.message || error.toString();
};
