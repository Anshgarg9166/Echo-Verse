import { View, Text } from 'react-native';

export default function History() {
  return (
    <View style={{ flex: 1, padding: 16 }}>
      <Text style={{ fontSize: 18, fontWeight: '600' }}>History</Text>
      <Text>Saved transcripts will appear here.</Text>
    </View>
  );
}
