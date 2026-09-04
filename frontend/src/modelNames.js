const MODEL_NAMES = {
  'minimax/minimax-m3:free': 'MiniMax M3',
  'openrouter/free': 'OpenRouter Free',
  'nvidia/nemotron-3-super-120b-a12b:free': 'Nemotron 3 Super',
};

export function getModelDisplayName(model) {
  if (!model) {
    return 'Unknown Model';
  }

  if (MODEL_NAMES[model]) {
    return MODEL_NAMES[model];
  }

  const shortName = model.split('/').pop() || model;

  return shortName
    .replace(/:free$/i, '')
    .replace(/[-_]+/g, ' ')
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}