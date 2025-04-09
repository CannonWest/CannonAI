/**
 * Utility for estimating token counts
 * Note: This is a very rough estimate. For accurate counts, you would need a tokenizer like GPT-2/3 BPE
 */

/**
 * Simple token estimator for displaying approximate token counts.
 * This is a rough approximation - actual tokenization will vary by model.
 * 
 * For production use, consider using a more accurate tokenizer like:
 * - GPT-3 Tokenizer (https://github.com/latitudegames/GPT-3-Encoder)
 * - tiktoken (for Python)
 */

// Very rough approximation - for English text:
// 1 token ≈ 4 characters or 0.75 words
export const estimateTokenCount = (text) => {
  if (!text) return 0;
  
  // Remove excess whitespace
  const trimmedText = text.trim().replace(/\s+/g, ' ');
  
  // Count characters and words
  const charCount = trimmedText.length;
  const wordCount = trimmedText.split(' ').length;
  
  // Use the average of character-based and word-based estimates
  const charBasedEstimate = Math.ceil(charCount / 4);
  const wordBasedEstimate = Math.ceil(wordCount / 0.75);
  
  // Return the average, with a minimum of 1 token for any non-empty text
  return Math.max(1, Math.round((charBasedEstimate + wordBasedEstimate) / 2));
};

// For more accurate estimation, this function can be replaced with
// a proper tokenizer implementation in the future

// More refined estimation based on word boundaries and special tokens
export const estimateTokenCountBetter = (text) => {
  if (!text) return 0;
  
  // Split on word boundaries (very simplified)
  const words = text.split(/\s+/);
  
  // Count tokens (roughly 3/4 of a word is a token in many languages)
  let tokenCount = 0;
  for (const word of words) {
    // Common punctuation and small words are often 1 token
    if (word.length <= 2) {
      tokenCount += 1;
    } else {
      // Longer words might be multiple tokens
      tokenCount += Math.ceil(word.length / 4);
    }
  }
  
  return Math.max(1, tokenCount);
};

export const estimateTokensInConversation = (messages) => {
  if (!messages || !Array.isArray(messages)) return 0;
  
  // Add system message tokens if present
  const systemMessageTokens = messages.find(m => m.role === 'system')
    ? estimateTokenCount(messages.find(m => m.role === 'system').content)
    : 0;
  
  // Count tokens in each message with role overhead
  // Each message has ~4 tokens of overhead from formatting
  const MESSAGE_OVERHEAD_TOKENS = 4;
  
  const contentTokens = messages.reduce((total, message) => {
    return total + estimateTokenCount(message.content) + MESSAGE_OVERHEAD_TOKENS;
  }, 0);
  
  // Add a small fixed overhead for the conversation formatting
  const CONVERSATION_OVERHEAD = 3;
  
  return contentTokens + CONVERSATION_OVERHEAD;
};

export const getTokenLimit = (model) => {
  const tokenLimits = {
    'gpt-4o': 128000,
    'gpt-4o-mini': 128000,
    'gpt-4': 8192,
    'gpt-3.5-turbo': 16384,
    'gpt-4-turbo': 128000,
    'o1': 200000,
    'o1-mini': 128000,
    'o3-mini': 200000,
    'davinci-002': 16384,
    'deepseek-chat': 64000,
    'deepseek-reasoner': 64000
  };
  
  return tokenLimits[model] || 8000; // Default fallback
};
