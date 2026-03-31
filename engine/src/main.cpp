#include "Diverter.h"
#include <iostream>
#include <string>
#include <vector>
#include <algorithm>

int main() {
    std::cout << "WinDivert Evasion Engine" << std::endl;
    Diverter diverter;

    bool tcp_sni = true;
    bool udp_spoof = true;

    std::string whitelist_str;
    std::getline(std::cin, whitelist_str);
    
    std::vector<std::string> allowed_procs;
    size_t pos = 0;
    while ((pos = whitelist_str.find(',')) != std::string::npos) {
        std::string token = whitelist_str.substr(0, pos);
        // Trim spaces
        token.erase(token.begin(), std::find_if(token.begin(), token.end(), [](unsigned char ch) { return !std::isspace(ch); }));
        token.erase(std::find_if(token.rbegin(), token.rend(), [](unsigned char ch) { return !std::isspace(ch); }).base(), token.end());
        
        if (!token.empty()) allowed_procs.push_back(token);
        whitelist_str.erase(0, pos + 1);
    }
    // Handle last token
    whitelist_str.erase(whitelist_str.begin(), std::find_if(whitelist_str.begin(), whitelist_str.end(), [](unsigned char ch) { return !std::isspace(ch); }));
    whitelist_str.erase(std::find_if(whitelist_str.rbegin(), whitelist_str.rend(), [](unsigned char ch) { return !std::isspace(ch); }).base(), whitelist_str.end());
    if (!whitelist_str.empty()) allowed_procs.push_back(whitelist_str);

    if (!diverter.Start(tcp_sni, udp_spoof, allowed_procs)) {
        std::cerr << "Engine failed to start." << std::endl;
        return 1;
    }

    std::string cmd;
    while (std::getline(std::cin, cmd)) {
        if (!cmd.empty() && cmd.back() == '\r') cmd.pop_back();
        if (cmd == "stop" || cmd == "quit" || cmd == "exit") {
            break;
        }
    }

    diverter.Stop();
    return 0;
}
