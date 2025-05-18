import React, { useState, useEffect } from 'react';
import {
  Box,
  Typography,
  TextField,
  Button,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Slider,
  FormGroup,
  FormControlLabel,
  Switch,
  Paper,
  CircularProgress,
  Alert,
  InputAdornment,
  IconButton,
} from '@mui/material';
import { Visibility, VisibilityOff } from '@mui/icons-material';
import { getConfig, updateConfig, listModels, selectModel } from '../services/api';

const SettingsPanel = ({ config, setConfig }) => {
  // State for settings
  const [apiKey, setApiKey] = useState('');
  const [showApiKey, setShowApiKey] = useState(false);
  const [conversationsDir, setConversationsDir] = useState('');
  const [selectedModel, setSelectedModel] = useState('');
  const [availableModels, setAvailableModels] = useState([]);
  const [temperature, setTemperature] = useState(0.7);
  const [maxOutputTokens, setMaxOutputTokens] = useState(800);
  const [topP, setTopP] = useState(0.95);
  const [topK, setTopK] = useState(40);
  const [useStreaming, setUseStreaming] = useState(true);
  
  // State for UI
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);
  const [modelsLoading, setModelsLoading] = useState(false);
  
  // Initialize with current config
  useEffect(() => {
    if (config) {
      // Don't set API key text, just note if it's set
      setApiKey(config.api_key_set ? '••••••••••••••••' : '');
      setConversationsDir(config.conversations_dir || '');
      setSelectedModel(config.default_model || '');
      
      // Set generation parameters
      if (config.generation_params) {
        setTemperature(config.generation_params.temperature || 0.7);
        setMaxOutputTokens(config.generation_params.max_output_tokens || 800);
        setTopP(config.generation_params.top_p || 0.95);
        setTopK(config.generation_params.top_k || 40);
      }
    }
    
    // Load available models
    loadModels();
  }, [config]);
  
  // Load available models
  const loadModels = async () => {
    try {
      setModelsLoading(true);
      const models = await listModels();
      setAvailableModels(models);
    } catch (error) {
      console.error('Failed to load models:', error);
      setError('Failed to load available models. Please check your API key.');
    } finally {
      setModelsLoading(false);
    }
  };
  
  // Handle saving settings
  const handleSaveSettings = async () => {
    try {
      setLoading(true);
      setError(null);
      setSuccess(null);
      
      // Prepare update data
      const updateData = {
        api_key: apiKey === '••••••••••••••••' ? null : apiKey, // Only send if changed
        conversations_dir: conversationsDir,
        default_model: selectedModel,
        generation_params: {
          temperature,
          max_output_tokens: maxOutputTokens,
          top_p: topP,
          top_k: topK
        }
      };
      
      // Update config
      await updateConfig(updateData);
      
      // Update model if changed
      if (selectedModel !== config.default_model) {
        await selectModel(selectedModel);
      }
      
      // Refresh config
      const updatedConfig = await getConfig();
      setConfig(updatedConfig);
      
      setSuccess('Settings saved successfully');
    } catch (error) {
      console.error('Failed to save settings:', error);
      setError('Failed to save settings: ' + (error.message || 'Unknown error'));
    } finally {
      setLoading(false);
    }
  };
  
  return (
    <Box sx={{ p: 3, maxWidth: '800px', mx: 'auto' }}>
      <Typography variant="h4" gutterBottom>
        Settings
      </Typography>
      
      <Paper sx={{ p: 3, mb: 4 }}>
        <Typography variant="h6" gutterBottom>
          API Configuration
        </Typography>
        
        <FormControl fullWidth sx={{ mb: 3 }}>
          <TextField
            label="Gemini API Key"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            type={showApiKey ? 'text' : 'password'}
            helperText="Your Google Gemini API key for accessing the models"
            InputProps={{
              endAdornment: (
                <InputAdornment position="end">
                  <IconButton
                    aria-label="toggle password visibility"
                    onClick={() => setShowApiKey(!showApiKey)}
                    edge="end"
                  >
                    {showApiKey ? <VisibilityOff /> : <Visibility />}
                  </IconButton>
                </InputAdornment>
              )
            }}
          />
        </FormControl>
        
        <FormControl fullWidth sx={{ mb: 3 }}>
          <TextField
            label="Conversations Directory"
            value={conversationsDir}
            onChange={(e) => setConversationsDir(e.target.value)}
            helperText="Directory where conversations are stored"
          />
        </FormControl>
      </Paper>
      
      <Paper sx={{ p: 3, mb: 4 }}>
        <Typography variant="h6" gutterBottom>
          Model Settings
        </Typography>
        
        <FormControl fullWidth sx={{ mb: 3 }}>
          <InputLabel>Default Model</InputLabel>
          <Select
            value={selectedModel}
            onChange={(e) => setSelectedModel(e.target.value)}
            label="Default Model"
            disabled={modelsLoading}
          >
            {modelsLoading ? (
              <MenuItem value="">
                <CircularProgress size={20} sx={{ mr: 1 }} />
                Loading models...
              </MenuItem>
            ) : (
              availableModels.map(model => (
                <MenuItem key={model.name} value={model.name}>
                  {model.display_name}
                </MenuItem>
              ))
            )}
          </Select>
        </FormControl>
        
        <Typography gutterBottom>
          Temperature: {temperature.toFixed(2)}
        </Typography>
        <Slider
          value={temperature}
          onChange={(_, value) => setTemperature(value)}
          min={0}
          max={2}
          step={0.01}
          valueLabelDisplay="auto"
          sx={{ mb: 3 }}
        />
        
        <Typography gutterBottom>
          Max Output Tokens: {maxOutputTokens}
        </Typography>
        <Slider
          value={maxOutputTokens}
          onChange={(_, value) => setMaxOutputTokens(value)}
          min={100}
          max={4096}
          step={100}
          valueLabelDisplay="auto"
          sx={{ mb: 3 }}
        />
        
        <Typography gutterBottom>
          Top P: {topP.toFixed(2)}
        </Typography>
        <Slider
          value={topP}
          onChange={(_, value) => setTopP(value)}
          min={0}
          max={1}
          step={0.01}
          valueLabelDisplay="auto"
          sx={{ mb: 3 }}
        />
        
        <Typography gutterBottom>
          Top K: {topK}
        </Typography>
        <Slider
          value={topK}
          onChange={(_, value) => setTopK(value)}
          min={1}
          max={100}
          step={1}
          valueLabelDisplay="auto"
          sx={{ mb: 3 }}
        />
        
        <FormGroup>
          <FormControlLabel
            control={
              <Switch
                checked={useStreaming}
                onChange={(e) => setUseStreaming(e.target.checked)}
              />
            }
            label="Streaming Mode"
          />
        </FormGroup>
      </Paper>
      
      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
        </Alert>
      )}
      
      {success && (
        <Alert severity="success" sx={{ mb: 2 }}>
          {success}
        </Alert>
      )}
      
      <Button
        variant="contained"
        color="primary"
        onClick={handleSaveSettings}
        disabled={loading}
        startIcon={loading && <CircularProgress size={20} />}
      >
        Save Settings
      </Button>
    </Box>
  );
};

export default SettingsPanel;
