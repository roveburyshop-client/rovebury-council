import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import { getModelDisplayName } from '../modelNames';
import './Stage1.css';


export default function Stage1({ responses }) {
  const [activeTab, setActiveTab] = useState(0);

  if (!responses || responses.length === 0) {
    return null;
  }

  const activeResponse = responses[activeTab];

  return (
    <div className="stage stage1">
      <h3 className="stage-title">
        Stage 1: Individual Responses
      </h3>

      <div className="tabs">
        {responses.map((response, index) => (
          <button
            key={response.model || index}
            type="button"
            className={`tab ${
              activeTab === index ? 'active' : ''
            }`}
            onClick={() => setActiveTab(index)}
          >
            {getModelDisplayName(response.model)}
          </button>
        ))}
      </div>

      <div className="tab-content">
        <div className="model-name">
          {getModelDisplayName(activeResponse.model)}
        </div>

        <div className="response-text markdown-content">
          <ReactMarkdown>
            {activeResponse.response}
          </ReactMarkdown>
        </div>
      </div>
    </div>
  );
}