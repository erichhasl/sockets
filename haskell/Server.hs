module Socket where

import qualified Network.Socket as Net
import qualified System.IO as Sys
import Control.Concurrent
import Control.Concurrent.Chan
import Control.Monad (forever)
import Control.Monad.Reader
import Data.List.Split

data Buffering = NoBuffering
               | LengthBuffering
               | DelimiterBuffering String
                 deriving (Show)

data ServerEnv = ServerEnv
    { buffering :: Buffering       -- ^ Buffermode
    , socket :: Net.Socket         -- ^ the socket used to communicate
    , global :: Chan String
    , onReceive :: OnReceive
    }

type Server = ReaderT ServerEnv IO

type OnReceive = Sys.Handle -> Net.SockAddr -> String -> Server ()

broadcast :: String -> Server ()
broadcast msg = do
    bufmode <- asks buffering
    chan <- asks global
    case bufmode of
        DelimiterBuffering delim -> liftIO $ writeChan chan $ msg ++ delim
        _                        -> liftIO $ writeChan chan msg

send :: Sys.Handle -> String -> Server ()
send connhdl msg = do
    bufmode <- asks buffering
    case bufmode of
        DelimiterBuffering delim -> liftIO $ Sys.hPutStr connhdl $ msg ++ delim
        _                        -> liftIO $ Sys.hPutStr connhdl msg


-- | Initialize a new server with the given port number and buffering mode
initServer :: Net.PortNumber -> Buffering -> OnReceive -> IO ServerEnv
initServer port buffermode handler = do
    sock <- Net.socket Net.AF_INET Net.Stream 0
    Net.setSocketOption sock Net.ReuseAddr 1
    Net.bind sock (Net.SockAddrInet port Net.iNADDR_ANY)
    Net.listen sock 5
    chan <- newChan
    forkIO $ forever $ do
        msg <- readChan chan -- clearing the main channel
        return ()
    return (ServerEnv buffermode sock chan handler)

-- | Looping over requests and establish connection
procRequests :: Server ()
procRequests = do
    sock <- asks socket
    (conn, clientaddr) <- liftIO $ Net.accept sock
    env <- ask
    liftIO $ forkIO $ runReaderT (procMessages conn clientaddr) env
    procRequests

-- | Handle one client
procMessages :: Net.Socket -> Net.SockAddr -> Server ()
procMessages conn clientaddr = do
    connhdl <- liftIO $ Net.socketToHandle conn Sys.ReadWriteMode
    liftIO $ Sys.hSetBuffering connhdl Sys.NoBuffering
    globalChan <- asks global

    commChan <- liftIO $ dupChan globalChan

    reader <- liftIO $ forkIO $ forever $ do
        msg <- readChan commChan
        Sys.hPutStrLn connhdl msg

    handler <- asks onReceive
    messages <- liftIO $ Sys.hGetContents connhdl
    buffermode <- asks buffering
    case buffermode of
        DelimiterBuffering delimiter ->
            mapM_ (handler connhdl clientaddr) (splitOn delimiter messages)
        LengthBuffering -> liftIO $ putStrLn (take 4 messages)
        _ -> return ()

    -- clean up
    liftIO $ do killThread reader
                Sys.hClose connhdl

sampleHandler :: OnReceive
sampleHandler connhdl addr query = do
    liftIO $ putStrLn $ "new query " ++ query
    send connhdl $ "> " ++ query

main :: IO ()
main = do
    env <- initServer 4242 LengthBuffering sampleHandler
    runReaderT procRequests env
