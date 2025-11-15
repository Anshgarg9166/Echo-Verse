import { View, Text, Button } from 'react-native';
import { useState } from 'react';

export default function LiveCaption() {
  const [isRecording, setRecording] = useState(false);
  const [transcript, setTranscript] = useState('');
  const [translation, setTranslation] = useState('');

  // TODO: integrate audio capture (expo-audio) & call Flask /process
  return (
    <View style={{ flex: 1, padding: 16, gap: 16 }}>
      <Text style={{ fontSize: 18, fontWeight: '700' }}>Live Caption & Translate</Text>
      <Button
        title={isRecording ? "Stop" : "Start Recording"}
        onPress={() => setRecording(!isRecording)}
      />
      <Text style={{ marginTop: 20 }}>Transcript: {transcript || '—'}</Text>
      <Text>Translation: {translation || '—'}</Text>
    </View>
  );
}
