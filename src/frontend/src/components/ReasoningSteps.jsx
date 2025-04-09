import React, { useState } from 'react';
import ReactMarkdown from 'react-markdown';

// Simple code block renderer with no dependencies
const SimpleCodeBlock = ({ children, className }) => {
  // Extract language from className if available
  const language = className ? className.replace('language-', '') : '';
  return (
    <pre className={`code-block ${language ? `language-${language}` : ''}`}>
      <code>{children}</code>
    </pre>
  );
};

const ReasoningSteps = ({ steps }) => {
  const [expanded, setExpanded] = useState(false);
  
  if (!steps || steps.length === 0) {
    return null;
  }
  
  // First step is often most revealing - show a preview
  const previewStep = steps[0];
  
  return (
    <div className="reasoning-steps">
      <div className="reasoning-header" onClick={() => setExpanded(!expanded)}>
        <h4>
          <span className={`expand-icon ${expanded ? 'expanded' : ''}`}>▶</span>
          AI's Reasoning Process ({steps.length} steps)
        </h4>
      </div>
      
      {!expanded ? (
        <div className="reasoning-preview">
          <p>
            <strong>{previewStep.name || 'First Step'}</strong>: {' '}
            {previewStep.content.length > 100 
              ? previewStep.content.substring(0, 100) + '...'
              : previewStep.content
            }
          </p>
          <button onClick={() => setExpanded(true)} className="reasoning-expand-btn">
            Show Full Reasoning
          </button>
        </div>
      ) : (
        <div className="reasoning-details">
          {steps.map((step, index) => (
            <div key={index} className="reasoning-step">
              <h5>{step.name || `Step ${index + 1}`}</h5>
              <div className="step-content">
                <ReactMarkdown components={{ code: SimpleCodeBlock }}>
                  {step.content}
                </ReactMarkdown>
              </div>
            </div>
          ))}
          <button onClick={() => setExpanded(false)} className="reasoning-collapse-btn">
            Collapse Reasoning
          </button>
        </div>
      )}
    </div>
  );
};

export default ReasoningSteps;
