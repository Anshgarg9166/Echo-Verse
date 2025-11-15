import { Link } from 'expo-router';
import { View, Text, TextInput, Button } from 'react-native';
import { useState } from 'react';

export default function Signup() {
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [pw, setPw] = useState('');

  return (
    <View style={{ flex: 1, padding: 16, gap: 12, justifyContent: 'center' }}>
      <Text style={{ fontSize: 22, fontWeight: '700' }}>Create Account</Text>
      <TextInput placeholder="Name" onChangeText={setName} style={{ borderWidth: 1, padding: 10 }} />
      <TextInput placeholder="Email" onChangeText={setEmail} autoCapitalize="none" style={{ borderWidth: 1, padding: 10 }} />
      <TextInput placeholder="Password" onChangeText={setPw} secureTextEntry style={{ borderWidth: 1, padding: 10 }} />
      <Button title="Sign up" onPress={() => { /* TODO: call Flask */ }} />
      <Link href="/auth/login">Already have an account?</Link>
    </View>
  );
}
