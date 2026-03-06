# backend/app/services/session_engine.py
class SessionEngine:
    @staticmethod
    def analyze_sessions(df):
        """
        Determine buy/sell dominance per session
        """
        sessions = {'London':'neutral','NY':'neutral','Asia':'neutral'}
        # placeholder: randomly assign for example
        sessions['London'] = 'buy'
        sessions['NY'] = 'sell'
        sessions['Asia'] = 'buy'
        return sessions
