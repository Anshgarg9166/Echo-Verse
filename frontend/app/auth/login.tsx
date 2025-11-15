import { Link } from 'expo-router';
import { View, Text, TextInput, Button } from 'react-native';
import { useState } from 'react';

export default function Login() {
  const [email, setEmail] = useState('');
  const [pw, setPw] = useState('');
  return (
    <View style={{ flex: 1, padding: 16, gap: 12, justifyContent: 'center' }}>
      <Text style={{ fontSize: 22, fontWeight: '700' }}>Login</Text>
      <TextInput placeholder="Email" onChangeText={setEmail} autoCapitalize="none" style={{ borderWidth: 1, padding: 10 }} />
      <TextInput placeholder="Password" onChangeText={setPw} secureTextEntry style={{ borderWidth: 1, padding: 10 }} />
      <Button title="Login" onPress={() => { /* TODO: call Flask */ }} />
      <Link href="/auth/signup">Create account</Link>
      <Link href="/(tabs)">Skip for now →</Link>
    </View>
  );
}
