import { useNavigate } from 'react-router-dom';
import { FiMessageSquare, FiPlus } from 'react-icons/fi';
import { getDefaultConversation } from '../services/api';

const HomePage = () => {
  const navigate = useNavigate();

  const handleNewConversation = async () => {
    try {
      // Get or create the default conversation
      const defaultConversation = await getDefaultConversation();
      navigate(`/conversation/${defaultConversation.id}`);
    } catch (error) {
      console.error('Failed to get default conversation:', error);
      // Fallback to the new conversation route which will also try
      // to get the default conversation in the ConversationPage component
      navigate('/conversation/new');
    }
  };

  return (
    <div className="flex flex-col items-center justify-center h-full max-w-3xl mx-auto px-4 py-8">
      <div className="text-center">
        <div className="mb-6 p-4 bg-blue-100 dark:bg-blue-900 rounded-full inline-block">
          <FiMessageSquare className="h-12 w-12 text-blue-600 dark:text-blue-300" />
        </div>
        <h1 className="text-3xl font-bold text-gray-800 dark:text-white mb-2">
          Welcome to AI Chat Manager
        </h1>
        <p className="text-gray-600 dark:text-gray-300 mb-8 max-w-lg mx-auto">
          Your gateway to conversations with AI models. Choose from various providers,
          customize settings, and manage all your AI chats in one place.
        </p>
        
        <button
          onClick={handleNewConversation}
          className="inline-flex items-center px-6 py-3 bg-blue-600 text-white font-medium rounded-md shadow-sm hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
        >
          <FiPlus className="mr-2" />
          Start a New Conversation
        </button>
      </div>
      
      <div className="mt-16 grid gap-8 grid-cols-1 md:grid-cols-2 w-full">
        <FeatureCard 
          title="Multiple AI Models"
          description="Connect with different AI providers like OpenAI, Google, and more."
        />
        <FeatureCard 
          title="Customizable Settings"
          description="Adjust temperature, max tokens, and other model-specific parameters."
        />
        <FeatureCard 
          title="Conversation Management"
          description="Save, organize, and revisit your conversation threads anytime."
        />
        <FeatureCard 
          title="Dark Mode Support"
          description="Choose between light and dark themes for comfortable viewing."
        />
      </div>
    </div>
  );
};

interface FeatureCardProps {
  title: string;
  description: string;
}

const FeatureCard = ({ title, description }: FeatureCardProps) => {
  return (
    <div className="p-6 bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-100 dark:border-gray-700">
      <h3 className="text-lg font-medium text-gray-800 dark:text-white mb-2">{title}</h3>
      <p className="text-gray-600 dark:text-gray-300">{description}</p>
    </div>
  );
};

export default HomePage;
