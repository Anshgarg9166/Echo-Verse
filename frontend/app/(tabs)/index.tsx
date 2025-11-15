import { Link } from 'expo-router';
import { View, Text, Button } from 'react-native';

export default function Dashboard() {
  return (
    <View style={{ flex: 1, padding: 16, gap: 16, justifyContent: 'center' }}>
      <Text style={{ fontSize: 22, fontWeight: '600' }}>EchoVerse</Text>
      <Text>Real-time speech translation & captioning</Text>
      <Link href="/live/caption" asChild>
        <Button title="Start Live Caption & Translate" />
      </Link>
    </View>
  );
}
