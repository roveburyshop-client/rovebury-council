import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import { getModelDisplayName } from '../modelNames';
import './Stage2.css';


function deAnonymizeText(text, labelToModel) {
  if (!labelToModel) {
    return text;
  }

  let result = text;

  Object.entries(labelToModel).forEach(
    ([label, model]) => {
      const displayName = getModelDisplayName(model);

      result = result.replace(
        new RegExp(label, 'g'),
        `**${displayName}**`
      );
    }
  );

  return result;
}


export default function Stage2({
  rankings,
  labelToModel,
  aggregateRankings,
}) {
  const [activeTab, setActiveTab] = useState(0);

  if (!rankings || rankings.length === 0) {
    return null;
  }

  const activeRanking = rankings[activeTab];

  return (
    <div className="stage stage2">
      <h3 className="stage-title">
        Stage 2: Peer Rankings
      </h3>

      <h4>Raw Evaluations</h4>

      <p className="stage-description">
        Each model evaluated the anonymized responses
        independently. Model names are restored below for
        readability.
      </p>

      <div className="tabs">
        {rankings.map((ranking, index) => (
          <button
            key={ranking.model || index}
            type="button"
            className={`tab ${
              activeTab === index ? 'active' : ''
            }`}
            onClick={() => setActiveTab(index)}
          >
            {getModelDisplayName(ranking.model)}
          </button>
        ))}
      </div>

      <div className="tab-content">
        <div className="ranking-model">
          {getModelDisplayName(activeRanking.model)}
        </div>

        <div className="ranking-content markdown-content">
          <ReactMarkdown>
            {deAnonymizeText(
              activeRanking.ranking,
              labelToModel
            )}
          </ReactMarkdown>
        </div>

        {activeRanking.parsed_ranking &&
          activeRanking.parsed_ranking.length > 0 && (
            <div className="parsed-ranking">
              <strong>Extracted Ranking:</strong>

              <ol>
                {activeRanking.parsed_ranking.map(
                  (label, index) => {
                    const model = labelToModel?.[label];

                    return (
                      <li key={`${label}-${index}`}>
                        {model
                          ? getModelDisplayName(model)
                          : label}
                      </li>
                    );
                  }
                )}
              </ol>
            </div>
          )}
      </div>

      {aggregateRankings &&
        aggregateRankings.length > 0 && (
          <div className="aggregate-rankings">
            <h4>
              Aggregate Rankings (Street Cred)
            </h4>

            <p className="stage-description">
              Combined peer evaluations. Lower average rank
              is better.
            </p>

            <div className="aggregate-list">
              {aggregateRankings.map(
                (aggregate, index) => (
                  <div
                    key={aggregate.model || index}
                    className="aggregate-item"
                  >
                    <span className="rank-position">
                      #{index + 1}
                    </span>

                    <span className="rank-model">
                      {getModelDisplayName(
                        aggregate.model
                      )}
                    </span>

                    <span className="rank-score">
                      Avg:{' '}
                      {Number(
                        aggregate.average_rank
                      ).toFixed(2)}
                    </span>

                    <span className="rank-count">
                      ({aggregate.rankings_count}{' '}
                      votes)
                    </span>
                  </div>
                )
              )}
            </div>
          </div>
        )}
    </div>
  );
}