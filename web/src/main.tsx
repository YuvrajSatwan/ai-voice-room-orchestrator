import '@fontsource-variable/inter';
import './styles/tokens.css';
import './styles/base.css';
import './features/participants/participants.css';
import './features/conversation/conversation.css';
import './features/voice/voice.css';
import './features/intelligence/intelligence.css';
import './features/room/room.css';
import './features/join/join.css';

import { createRoot } from 'react-dom/client';
import { App } from './app/App';
import { trackVisualViewport } from './app/viewport';

trackVisualViewport();

// No StrictMode: its double-mount in development would join the LiveKit room twice.
createRoot(document.getElementById('root')!).render(<App />);
