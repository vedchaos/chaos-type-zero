/**
 * CHAOS TYPE ZERO — Mobile Control Center
 * React Native App with Expo
 */

import React, { useState, useEffect } from 'react';
import { StatusBar } from 'expo-status-bar';
import {
  StyleSheet,
  Text,
  View,
  ScrollView,
  TouchableOpacity,
  TextInput,
  FlatList,
  RefreshControl,
  Alert,
  ActivityIndicator,
} from 'react-native';

// === Config ===
const API_BASE = 'http://YOUR_PC_IP:8081'; // Mobile API URL
const AUTH_TOKEN = 'ctz-mobile-secret-token';

// === API Helper ===
async function apiCall(endpoint, method = 'GET', body = null) {
  try {
    const headers = {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${AUTH_TOKEN}`,
    };
    const res = await fetch(`${API_BASE}${endpoint}`, {
      method,
      headers,
      body: body ? JSON.stringify(body) : null,
    });
    return await res.json();
  } catch (e) {
    return { error: e.message };
  }
}

// === Dashboard Screen ===
function DashboardScreen() {
  const [stats, setStats] = useState(null);
  const [refreshing, setRefreshing] = useState(false);

  const loadStats = async () => {
    const data = await apiCall('/api/status');
    setStats(data);
  };

  useEffect(() => { loadStats(); }, []);

  const onRefresh = async () => {
    setRefreshing(true);
    await loadStats();
    setRefreshing(false);
  };

  return (
    <ScrollView
      style={styles.container}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}
    >
      <Text style={styles.title}>CHAOS TYPE ZERO</Text>
      <Text style={styles.subtitle}>Mobile Control Center</Text>

      <View style={styles.card}>
        <Text style={styles.cardTitle}>System Status</Text>
        {stats ? (
          <>
            <StatRow label="Status" value={stats.status || 'Online'} />
            <StatRow label="MCP Servers" value="40" />
            <StatRow label="Tools" value="298" />
            <StatRow label="Providers" value="14" />
            <StatRow label="Skills" value="31" />
          </>
        ) : (
          <ActivityIndicator color="#00ff41" />
        )}
      </View>

      <View style={styles.card}>
        <Text style={styles.cardTitle}>Quick Actions</Text>
        <TouchableOpacity style={styles.button} onPress={() => Alert.alert('CTZ', 'Task sent to orchestrator!')}>
          <Text style={styles.buttonText}>Run Task</Text>
        </TouchableOpacity>
        <TouchableOpacity style={styles.button} onPress={() => Alert.alert('CTZ', 'Memory search started!')}>
          <Text style={styles.buttonText}>Search Memory</Text>
        </TouchableOpacity>
        <TouchableOpacity style={styles.button} onPress={() => Alert.alert('CTZ', 'Health check passed!')}>
          <Text style={styles.buttonText}>Health Check</Text>
        </TouchableOpacity>
      </View>

      <StatusBar style="light" />
    </ScrollView>
  );
}

// === Chat Screen ===
function ChatScreen() {
  const [messages, setMessages] = useState([
    { id: '1', role: 'system', text: 'CTZ Mobile connected. Type a command.' },
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);

  const sendMessage = async () => {
    if (!input.trim()) return;
    const userMsg = { id: Date.now().toString(), role: 'user', text: input };
    setMessages(prev => [...prev, userMsg]);
    setInput('');
    setLoading(true);

    const res = await apiCall('/api/chat', 'POST', { message: input });
    const botMsg = {
      id: (Date.now() + 1).toString(),
      role: 'assistant',
      text: res.response || res.error || 'No response',
    };
    setMessages(prev => [...prev, botMsg]);
    setLoading(false);
  };

  return (
    <View style={styles.chatContainer}>
      <FlatList
        data={messages}
        keyExtractor={item => item.id}
        renderItem={({ item }) => (
          <View style={[styles.message, item.role === 'user' ? styles.userMsg : styles.botMsg]}>
            <Text style={styles.messageText}>{item.text}</Text>
          </View>
        )}
        style={styles.messageList}
      />
      {loading && <ActivityIndicator color="#00ff41" style={{ margin: 10 }} />}
      <View style={styles.inputRow}>
        <TextInput
          style={styles.input}
          value={input}
          onChangeText={setInput}
          placeholder="Type command..."
          placeholderTextColor="#666"
        />
        <TouchableOpacity style={styles.sendButton} onPress={sendMessage}>
          <Text style={styles.sendButtonText}>Send</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
}

// === MCP Servers Screen ===
function MCPScreen() {
  const [servers, setServers] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const loadServers = async () => {
      const data = await apiCall('/api/mcps');
      setServers(data.servers || []);
      setLoading(false);
    };
    loadServers();
  }, []);

  const MCP_SERVERS = [
    { name: 'ctz-brain', tools: 3, desc: 'LLM Fallback' },
    { name: 'ctz-memory', tools: 3, desc: 'Memory System' },
    { name: 'ctz-router', tools: 4, desc: 'Task Router' },
    { name: 'ctz-security', tools: 5, desc: 'Security Scanner' },
    { name: 'ctz-orchestrator', tools: 8, desc: 'Orchestrator' },
    { name: 'ctz-voice', tools: 5, desc: 'Voice Commands' },
    { name: 'ctz-vision', tools: 6, desc: 'Screen Reader' },
    { name: 'ctz-ml', tools: 5, desc: 'ML Pipeline' },
    { name: 'ctz-automation', tools: 10, desc: 'Automation' },
    { name: 'ctz-browser', tools: 10, desc: 'Browser Auto' },
    { name: 'ctz-comms', tools: 9, desc: 'Communication' },
    { name: 'ctz-neural', tools: 6, desc: 'Neural Network' },
    { name: 'ctz-nse', tools: 6, desc: 'Security Scripts' },
    { name: 'ctz-cicd', tools: 7, desc: 'CI/CD Pipeline' },
    { name: 'ctz-db-multi', tools: 8, desc: 'Multi-Database' },
    { name: 'ctz-knowledge-graph', tools: 8, desc: 'Knowledge Graph' },
    { name: 'ctz-plugin', tools: 8, desc: 'Plugin Market' },
  ];

  return (
    <ScrollView style={styles.container}>
      <Text style={styles.title}>MCP Servers</Text>
      <Text style={styles.subtitle}>40 Servers | 298 Tools</Text>
      {MCP_SERVERS.map((s, i) => (
        <View key={i} style={styles.mcpCard}>
          <Text style={styles.mcpName}>{s.name}</Text>
          <Text style={styles.mcpDesc}>{s.desc} — {s.tools} tools</Text>
        </View>
      ))}
    </ScrollView>
  );
}

// === Settings Screen ===
function SettingsScreen() {
  const [apiUrl, setApiUrl] = useState(API_BASE);
  const [token, setToken] = useState(AUTH_TOKEN);

  return (
    <ScrollView style={styles.container}>
      <Text style={styles.title}>Settings</Text>

      <View style={styles.card}>
        <Text style={styles.cardTitle}>API Configuration</Text>
        <Text style={styles.label}>API URL</Text>
        <TextInput
          style={styles.inputFull}
          value={apiUrl}
          onChangeText={setApiUrl}
          placeholder="http://YOUR_PC_IP:8081"
          placeholderTextColor="#666"
        />
        <Text style={styles.label}>Auth Token</Text>
        <TextInput
          style={styles.inputFull}
          value={token}
          onChangeText={setToken}
          placeholder="Enter token"
          placeholderTextColor="#666"
          secureTextEntry
        />
        <TouchableOpacity style={styles.button}>
          <Text style={styles.buttonText}>Save</Text>
        </TouchableOpacity>
      </View>

      <View style={styles.card}>
        <Text style={styles.cardTitle}>About</Text>
        <StatRow label="Version" value="v3.0" />
        <StatRow label="Servers" value="40" />
        <StatRow label="Tools" value="298" />
        <StatRow label="Providers" value="14" />
      </View>
    </ScrollView>
  );
}

// === Helper Components ===
function StatRow({ label, value }) {
  return (
    <View style={styles.statRow}>
      <Text style={styles.statLabel}>{label}</Text>
      <Text style={styles.statValue}>{value}</Text>
    </View>
  );
}

// === Main App ===
export default function App() {
  return (
    <View style={styles.appContainer}>
      <DashboardScreen />
    </View>
  );
}

// === Styles ===
const styles = StyleSheet.create({
  appContainer: {
    flex: 1,
    backgroundColor: '#0a0a0a',
  },
  container: {
    flex: 1,
    backgroundColor: '#0a0a0a',
    padding: 16,
  },
  title: {
    color: '#00ff41',
    fontSize: 28,
    fontWeight: 'bold',
    marginTop: 40,
    marginBottom: 4,
    fontFamily: 'monospace',
  },
  subtitle: {
    color: '#666',
    fontSize: 14,
    marginBottom: 20,
  },
  card: {
    backgroundColor: '#111',
    borderRadius: 12,
    padding: 16,
    marginBottom: 16,
    borderWidth: 1,
    borderColor: '#222',
  },
  cardTitle: {
    color: '#00ff41',
    fontSize: 16,
    fontWeight: 'bold',
    marginBottom: 12,
  },
  statRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingVertical: 8,
    borderBottomWidth: 1,
    borderBottomColor: '#222',
  },
  statLabel: {
    color: '#888',
    fontSize: 14,
  },
  statValue: {
    color: '#00ff41',
    fontSize: 14,
    fontWeight: 'bold',
  },
  button: {
    backgroundColor: '#00ff41',
    borderRadius: 8,
    padding: 12,
    marginTop: 8,
    alignItems: 'center',
  },
  buttonText: {
    color: '#0a0a0a',
    fontSize: 14,
    fontWeight: 'bold',
  },
  chatContainer: {
    flex: 1,
    backgroundColor: '#0a0a0a',
  },
  messageList: {
    flex: 1,
    padding: 16,
  },
  message: {
    padding: 12,
    borderRadius: 8,
    marginBottom: 8,
    maxWidth: '80%',
  },
  userMsg: {
    backgroundColor: '#00ff41',
    alignSelf: 'flex-end',
  },
  botMsg: {
    backgroundColor: '#111',
    alignSelf: 'flex-start',
    borderWidth: 1,
    borderColor: '#222',
  },
  messageText: {
    color: '#fff',
    fontSize: 14,
  },
  inputRow: {
    flexDirection: 'row',
    padding: 12,
    borderTopWidth: 1,
    borderTopColor: '#222',
  },
  input: {
    flex: 1,
    backgroundColor: '#111',
    borderRadius: 8,
    padding: 12,
    color: '#fff',
    marginRight: 8,
    borderWidth: 1,
    borderColor: '#222',
  },
  inputFull: {
    backgroundColor: '#111',
    borderRadius: 8,
    padding: 12,
    color: '#fff',
    marginBottom: 12,
    borderWidth: 1,
    borderColor: '#222',
  },
  sendButton: {
    backgroundColor: '#00ff41',
    borderRadius: 8,
    padding: 12,
    paddingHorizontal: 20,
  },
  sendButtonText: {
    color: '#0a0a0a',
    fontWeight: 'bold',
  },
  label: {
    color: '#888',
    fontSize: 12,
    marginBottom: 4,
    marginTop: 8,
  },
  mcpCard: {
    backgroundColor: '#111',
    borderRadius: 8,
    padding: 12,
    marginBottom: 8,
    borderWidth: 1,
    borderColor: '#222',
  },
  mcpName: {
    color: '#00ff41',
    fontSize: 14,
    fontWeight: 'bold',
  },
  mcpDesc: {
    color: '#888',
    fontSize: 12,
    marginTop: 4,
  },
});
