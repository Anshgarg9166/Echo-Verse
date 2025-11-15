import { View, Text } from 'react-native';

export default function Settings() {
  return (
    <View style={{ flex: 1, padding: 16 }}>
      <Text style={{ fontSize: 18, fontWeight: '600' }}>Settings</Text>
      <Text>Language preferences, offline/online toggle, and more.</Text>
    </View>
  );
}
