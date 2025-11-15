import { Tabs, Stack } from 'expo-router';
import { useSegments } from 'expo-router';

export default function RootLayout() {
  // Tabs for main app; Stack for auth and deep screens
  return (
    <Stack screenOptions={{ headerShown: false }}>
      {/* Auth stack */}
      <Stack.Screen name="auth/login" />
      <Stack.Screen name="auth/signup" />

      {/* Tabs container (default route) */}
      <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
      
      {/* Live caption screen outside tabs (modal-style nav later) */}
      <Stack.Screen name="live/caption" />
    </Stack>
  );
}
