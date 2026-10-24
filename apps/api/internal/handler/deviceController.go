package handler

import (
	"crypto/ed25519"
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"os"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
	"time"

	"github.com/gorilla/mux"
	libp2pcrypto "github.com/libp2p/go-libp2p/core/crypto"
	libp2ppeer "github.com/libp2p/go-libp2p/core/peer"
	"github.com/silicium/internal/models"
	"gorm.io/gorm"
)

const devicePairingLifetime = 10 * time.Minute

var deviceNodeIDPattern = regexp.MustCompile(`^[A-Za-z0-9._-]{1,64}$`)
var miniworkerNodeIDPattern = regexp.MustCompile(`^miniworker-(0[1-9]|1[0-9]|2[0-4])$`)

type pairDeviceRequest struct {
	Code            string `json:"code"`
	NodeID          string `json:"nodeId"`
	PeerID          string `json:"peerId"`
	PublicKey       string `json:"publicKey"`
	Signature       string `json:"signature"`
	SolanaWallet    string `json:"solanaWallet"`
	SolanaSignature string `json:"solanaSignature"`
	PayoutWallet    string `json:"payoutWallet"`
}

type workerPayoutProofResponse struct {
	Message   string `json:"message"`
	Signature string `json:"signature"`
}

type userDeviceResponse struct {
	models.UserDevice
	WorkerPayoutProof *workerPayoutProofResponse `json:"workerPayoutProof,omitempty"`
}

type devicePairingCodesRequest struct {
	NodeIDs []string `json:"nodeIds"`
}

type devicePairingCodeResponse struct {
	NodeID    string    `json:"nodeId"`
	Code      string    `json:"code"`
	ExpiresAt time.Time `json:"expiresAt"`
}

type devicePairingQueuedResponse struct {
	NodeIDs   []string  `json:"nodeIds"`
	Count     int       `json:"count"`
	ExpiresAt time.Time `json:"expiresAt"`
}

func (h *Handler) ListUserDevices(w http.ResponseWriter, r *http.Request) {
	userID, ok := userIDFromRequest(r)
	if !ok {
		writeAuthJSON(w, http.StatusUnauthorized, map[string]string{"message": "La session n’est pas valide."})
		return
	}
	var devices []models.UserDevice
	if err := h.DB.WithContext(r.Context()).Where("user_id = ?", userID).Order("linked_at DESC, id DESC").Find(&devices).Error; err != nil {
		writeAuthJSON(w, http.StatusInternalServerError, map[string]string{"message": "Les appareils du compte sont indisponibles."})
		return
	}
	items := make([]userDeviceResponse, 0, len(devices))
	for _, device := range devices {
		item := userDeviceResponse{UserDevice: device}
		if device.WorkerPayoutProofMessage != "" && device.WorkerPayoutProofSignature != "" {
			item.WorkerPayoutProof = &workerPayoutProofResponse{
				Message:   device.WorkerPayoutProofMessage,
				Signature: device.WorkerPayoutProofSignature,
			}
		}
		items = append(items, item)
	}
	writeAuthJSON(w, http.StatusOK, map[string]any{"items": items})
}

func (h *Handler) CreateDevicePairingCode(w http.ResponseWriter, r *http.Request) {
	userID, ok := userIDFromRequest(r)
	if !ok {
		writeAuthJSON(w, http.StatusUnauthorized, map[string]string{"message": "La session n’est pas valide."})
		return
	}
	payoutWallet, err := verifiedPayoutWallet(h.DB.WithContext(r.Context()), userID)
	if err != nil {
		writeAuthJSON(w, http.StatusConflict, map[string]string{"message": "Associez d’abord un wallet Solana vérifié à votre compte pour recevoir les récompenses."})
		return
	}
	secret := make([]byte, 32)
	if _, err := rand.Read(secret); err != nil {
		writeAuthJSON(w, http.StatusInternalServerError, map[string]string{"message": "Le code d’association ne peut pas être créé."})
		return
	}
	code := hex.EncodeToString(secret)
	digest := sha256.Sum256([]byte(code))
	now := time.Now().UTC()
	challenge := models.DevicePairingCode{UserID: userID, PayoutWallet: payoutWallet, CodeHash: hex.EncodeToString(digest[:]), ExpiresAt: now.Add(devicePairingLifetime)}
	err = h.DB.WithContext(r.Context()).Transaction(func(tx *gorm.DB) error {
		if err := tx.Where("user_id = ? AND (consumed_at IS NOT NULL OR expires_at <= ?)", userID, now).Delete(&models.DevicePairingCode{}).Error; err != nil {
			return err
		}
		return tx.Create(&challenge).Error
	})
	if err != nil {
		writeAuthJSON(w, http.StatusInternalServerError, map[string]string{"message": "Le code d’association ne peut pas être créé."})
		return
	}
	w.Header().Set("Cache-Control", "no-store")
	writeAuthJSON(w, http.StatusCreated, map[string]any{"code": code, "expiresAt": challenge.ExpiresAt})
}

// CreateDevicePairingCodes issues independent, one-use codes bound to the
// requested miniworker IDs and writes each code only to that worker's private
// pairing mount. The browser never receives the codes or an account token.
func (h *Handler) CreateDevicePairingCodes(w http.ResponseWriter, r *http.Request) {
	userID, ok := userIDFromRequest(r)
	if !ok {
		writeAuthJSON(w, http.StatusUnauthorized, map[string]string{"message": "La session n’est pas valide."})
		return
	}
	payoutWallet, err := verifiedPayoutWallet(h.DB.WithContext(r.Context()), userID)
	if err != nil {
		writeAuthJSON(w, http.StatusConflict, map[string]string{"message": "Associez d’abord un wallet Solana vérifié à votre compte pour recevoir les récompenses."})
		return
	}
	pairingDir := strings.TrimSpace(os.Getenv("SILICIUM_DEVICE_PAIRING_DIR"))
	if !filepath.IsAbs(pairingDir) {
		writeAuthJSON(w, http.StatusServiceUnavailable, map[string]string{"message": "L’association directe du pool de machines n’est pas disponible sur ce serveur."})
		return
	}
	var req devicePairingCodesRequest
	if err := json.NewDecoder(http.MaxBytesReader(w, r.Body, 16<<10)).Decode(&req); err != nil || len(req.NodeIDs) < 1 || len(req.NodeIDs) > 24 {
		writeAuthJSON(w, http.StatusBadRequest, map[string]string{"message": "La liste des machines doit contenir entre 1 et 24 identifiants."})
		return
	}
	seen := make(map[string]struct{}, len(req.NodeIDs))
	items := make([]devicePairingCodeResponse, 0, len(req.NodeIDs))
	rows := make([]models.DevicePairingCode, 0, len(req.NodeIDs))
	nodeIDs := make([]string, 0, len(req.NodeIDs))
	now := time.Now().UTC()
	for _, rawNodeID := range req.NodeIDs {
		nodeID := strings.TrimSpace(rawNodeID)
		if !miniworkerNodeIDPattern.MatchString(nodeID) {
			writeAuthJSON(w, http.StatusBadRequest, map[string]string{"message": "Un identifiant de miniworker est invalide."})
			return
		}
		if _, exists := seen[nodeID]; exists {
			writeAuthJSON(w, http.StatusBadRequest, map[string]string{"message": "La liste contient un identifiant de machine en double."})
			return
		}
		seen[nodeID] = struct{}{}
		workerDir := filepath.Join(pairingDir, nodeID)
		info, statErr := os.Stat(workerDir)
		if statErr != nil || !info.IsDir() {
			writeAuthJSON(w, http.StatusServiceUnavailable, map[string]string{"message": "Les emplacements privés des miniworkers ne sont pas prêts sur ce serveur."})
			return
		}
		secret := make([]byte, 32)
		if _, err := rand.Read(secret); err != nil {
			writeAuthJSON(w, http.StatusInternalServerError, map[string]string{"message": "Les codes d’association ne peuvent pas être créés."})
			return
		}
		code := hex.EncodeToString(secret)
		digest := sha256.Sum256([]byte(code))
		expiresAt := now.Add(devicePairingLifetime)
		items = append(items, devicePairingCodeResponse{NodeID: nodeID, Code: code, ExpiresAt: expiresAt})
		nodeIDs = append(nodeIDs, nodeID)
		rows = append(rows, models.DevicePairingCode{UserID: userID, NodeID: nodeID, PayoutWallet: payoutWallet, CodeHash: hex.EncodeToString(digest[:]), ExpiresAt: expiresAt})
	}
	err = h.DB.WithContext(r.Context()).Transaction(func(tx *gorm.DB) error {
		var linkedElsewhere models.UserDevice
		if err := tx.Where("node_id IN ? AND user_id <> ?", nodeIDs, userID).First(&linkedElsewhere).Error; err == nil {
			return errors.New("miniworker_already_linked")
		} else if !errors.Is(err, gorm.ErrRecordNotFound) {
			return err
		}
		var pendingElsewhere models.DevicePairingCode
		if err := tx.Where("node_id IN ? AND user_id <> ? AND consumed_at IS NULL AND expires_at > ?", nodeIDs, userID, now).First(&pendingElsewhere).Error; err == nil {
			return errors.New("miniworker_pairing_active")
		} else if !errors.Is(err, gorm.ErrRecordNotFound) {
			return err
		}
		if err := tx.Where("user_id = ? AND (consumed_at IS NOT NULL OR expires_at <= ?)", userID, now).Delete(&models.DevicePairingCode{}).Error; err != nil {
			return err
		}
		for _, row := range rows {
			if err := tx.Where("user_id = ? AND node_id = ? AND consumed_at IS NULL", userID, row.NodeID).Delete(&models.DevicePairingCode{}).Error; err != nil {
				return err
			}
		}
		return tx.Create(&rows).Error
	})
	if err != nil {
		if err.Error() == "miniworker_already_linked" {
			writeAuthJSON(w, http.StatusConflict, map[string]string{"message": "Au moins un miniworker est déjà associé à un autre compte."})
			return
		}
		if err.Error() == "miniworker_pairing_active" {
			writeAuthJSON(w, http.StatusConflict, map[string]string{"message": "Un autre compte a déjà demandé l’association de ce pool."})
			return
		}
		writeAuthJSON(w, http.StatusInternalServerError, map[string]string{"message": "Les codes d’association ne peuvent pas être enregistrés."})
		return
	}
	for _, item := range items {
		if err := writeMiniworkerPairingCode(pairingDir, item.NodeID, item.Code, *payoutWallet); err != nil {
			for _, nodeID := range nodeIDs {
				_ = clearMiniworkerPairingCode(pairingDir, nodeID)
			}
			_ = h.DB.WithContext(r.Context()).Where("user_id = ? AND node_id IN ? AND consumed_at IS NULL", userID, nodeIDs).Delete(&models.DevicePairingCode{}).Error
			writeAuthJSON(w, http.StatusServiceUnavailable, map[string]string{"message": "Les codes sécurisés n’ont pas pu être transmis aux miniworkers."})
			return
		}
	}
	w.Header().Set("Cache-Control", "no-store")
	writeAuthJSON(w, http.StatusAccepted, devicePairingQueuedResponse{NodeIDs: nodeIDs, Count: len(nodeIDs), ExpiresAt: now.Add(devicePairingLifetime)})
}

func (h *Handler) PairDevice(w http.ResponseWriter, r *http.Request) {
	var req pairDeviceRequest
	if err := json.NewDecoder(http.MaxBytesReader(w, r.Body, 16<<10)).Decode(&req); err != nil {
		writeAuthJSON(w, http.StatusBadRequest, map[string]string{"message": "La preuve d’association est invalide."})
		return
	}
	req.Code = strings.TrimSpace(req.Code)
	req.NodeID = strings.TrimSpace(req.NodeID)
	req.PeerID = strings.TrimSpace(req.PeerID)
	if len(req.Code) != 64 || !deviceNodeIDPattern.MatchString(req.NodeID) || len(req.PeerID) == 0 || len(req.PeerID) > 128 {
		writeAuthJSON(w, http.StatusBadRequest, map[string]string{"message": "Le code ou l’identité de l’appareil est invalide."})
		return
	}
	codeBytes, err := hex.DecodeString(req.Code)
	if err != nil || len(codeBytes) != 32 {
		writeAuthJSON(w, http.StatusBadRequest, map[string]string{"message": "Le code d’association est invalide."})
		return
	}
	publicBytes, err := base64.StdEncoding.DecodeString(strings.TrimSpace(req.PublicKey))
	if err != nil {
		writeAuthJSON(w, http.StatusBadRequest, map[string]string{"message": "L’identité cryptographique de l’appareil est invalide."})
		return
	}
	publicKey, err := libp2pcrypto.UnmarshalPublicKey(publicBytes)
	if err != nil || publicKey.Type() != libp2pcrypto.Ed25519 {
		writeAuthJSON(w, http.StatusBadRequest, map[string]string{"message": "Cette identité d’appareil n’est pas prise en charge."})
		return
	}
	derivedPeerID, err := libp2ppeer.IDFromPublicKey(publicKey)
	if err != nil || derivedPeerID.String() != req.PeerID {
		writeAuthJSON(w, http.StatusUnauthorized, map[string]string{"message": "La clé ne correspond pas à l’identité du nœud."})
		return
	}
	signature, err := hex.DecodeString(strings.TrimSpace(req.Signature))
	if err != nil || len(signature) != 64 {
		writeAuthJSON(w, http.StatusBadRequest, map[string]string{"message": "La signature de l’appareil est invalide."})
		return
	}
	pairingPayload := devicePairingPayload(req.Code, req.NodeID, req.PeerID)
	var solanaWallet *string
	var payoutProofMessage string
	var payoutProofSignature string
	if req.SolanaWallet != "" || req.SolanaSignature != "" {
		req.SolanaWallet = strings.TrimSpace(req.SolanaWallet)
		wallet, walletErr := validateWalletAddress(req.SolanaWallet)
		walletSignature, signatureErr := hex.DecodeString(strings.TrimSpace(req.SolanaSignature))
		if walletErr != nil || signatureErr != nil || len(walletSignature) != ed25519.SignatureSize {
			writeAuthJSON(w, http.StatusBadRequest, map[string]string{"message": "La preuve du portefeuille du worker est invalide."})
			return
		}
		if strings.TrimSpace(req.PayoutWallet) != "" {
			req.PayoutWallet = strings.TrimSpace(req.PayoutWallet)
			if _, payoutErr := validateWalletAddress(req.PayoutWallet); payoutErr != nil {
				writeAuthJSON(w, http.StatusBadRequest, map[string]string{"message": "Le wallet de compte destiné aux récompenses est invalide."})
				return
			}
			pairingPayload = devicePairingPayoutPayload(req.Code, req.NodeID, req.PeerID, req.SolanaWallet, req.PayoutWallet)
			payoutProofMessage = string(pairingPayload)
			payoutProofSignature = hex.EncodeToString(walletSignature)
		} else {
			pairingPayload = devicePairingWalletPayload(req.Code, req.NodeID, req.PeerID, req.SolanaWallet)
		}
		if !ed25519.Verify(wallet[:], pairingPayload, walletSignature) {
			writeAuthJSON(w, http.StatusUnauthorized, map[string]string{"message": "La signature du portefeuille du worker ne correspond pas à cette machine."})
			return
		}
		walletAddress := req.SolanaWallet
		solanaWallet = &walletAddress
	}
	if valid, verifyErr := publicKey.Verify(pairingPayload, signature); verifyErr != nil || !valid {
		writeAuthJSON(w, http.StatusUnauthorized, map[string]string{"message": "La signature ne prouve pas le contrôle de cet appareil."})
		return
	}
	codeHash := devicePairingCodeHash(req.Code)
	now := time.Now().UTC()
	var linked models.UserDevice
	directPairingNodeID := ""
	err = h.DB.WithContext(r.Context()).Transaction(func(tx *gorm.DB) error {
		var pairing models.DevicePairingCode
		if err := tx.Where("code_hash = ?", codeHash).First(&pairing).Error; err != nil {
			return errors.New("pairing_code_invalid")
		}
		if pairing.NodeID != "" && pairing.NodeID != req.NodeID {
			return errors.New("pairing_code_node_mismatch")
		}
		if miniworkerNodeIDPattern.MatchString(pairing.NodeID) {
			directPairingNodeID = pairing.NodeID
		}
		if pairing.NodeID != "" && (solanaWallet == nil || pairing.PayoutWallet == nil || strings.TrimSpace(*pairing.PayoutWallet) == "") {
			return errors.New("pairing_wallet_proof_required")
		}
		if pairing.NodeID != "" && (req.PayoutWallet == "" || pairing.PayoutWallet == nil || !sameWallet(pairing.PayoutWallet, &req.PayoutWallet)) {
			return errors.New("pairing_payout_wallet_mismatch")
		}
		if pairing.PayoutWallet != nil {
			if _, err := validateWalletAddress(*pairing.PayoutWallet); err != nil {
				return errors.New("pairing_payout_wallet_invalid")
			}
		}
		if pairing.ConsumedAt != nil {
			var existing models.UserDevice
			if err := tx.Where("user_id = ? AND node_id = ? AND peer_id = ?", pairing.UserID, req.NodeID, req.PeerID).First(&existing).Error; err == nil {
				if !sameWallet(existing.SolanaWallet, solanaWallet) || !sameWallet(existing.PayoutWallet, pairing.PayoutWallet) {
					return errors.New("device_binding_conflict")
				}
				linked = existing
				return nil
			} else if !errors.Is(err, gorm.ErrRecordNotFound) {
				return err
			}
		}
		if pairing.ConsumedAt != nil || !pairing.ExpiresAt.After(now) {
			return errors.New("pairing_code_expired")
		}
		consumed := tx.Model(&models.DevicePairingCode{}).
			Where("id = ? AND consumed_at IS NULL AND expires_at > ?", pairing.ID, now).
			Update("consumed_at", now)
		if consumed.Error != nil {
			return consumed.Error
		}
		if consumed.RowsAffected != 1 {
			return errors.New("pairing_code_expired")
		}

		var byPeer models.UserDevice
		peerErr := tx.Where("peer_id = ?", req.PeerID).First(&byPeer).Error
		if peerErr != nil && !errors.Is(peerErr, gorm.ErrRecordNotFound) {
			return peerErr
		}
		var byNode models.UserDevice
		nodeErr := tx.Where("node_id = ?", req.NodeID).First(&byNode).Error
		if nodeErr != nil && !errors.Is(nodeErr, gorm.ErrRecordNotFound) {
			return nodeErr
		}
		hasPeer := peerErr == nil
		hasNode := nodeErr == nil
		if hasPeer && hasNode && byPeer.ID != byNode.ID {
			return errors.New("device_identity_conflict")
		}
		if hasPeer || hasNode {
			existing := byPeer
			if !hasPeer {
				existing = byNode
			}
			if existing.UserID != pairing.UserID {
				return errors.New("device_already_linked")
			}
			if solanaWallet != nil && existing.SolanaWallet != nil && *existing.SolanaWallet != *solanaWallet {
				return errors.New("device_wallet_conflict")
			}
		}
		if solanaWallet != nil {
			var walletOwner models.UserDevice
			walletErr := tx.Where("solana_wallet = ?", *solanaWallet).First(&walletOwner).Error
			if walletErr == nil {
				alreadyLinkedToDevice := (hasPeer && walletOwner.ID == byPeer.ID) || (hasNode && walletOwner.ID == byNode.ID)
				if !alreadyLinkedToDevice {
					return errors.New("worker_wallet_already_linked")
				}
			}
			if walletErr != nil && !errors.Is(walletErr, gorm.ErrRecordNotFound) {
				return walletErr
			}
		}
		if hasPeer || hasNode {
			existing := byPeer
			if !hasPeer {
				existing = byNode
			}
			existing.NodeID = req.NodeID
			existing.PeerID = req.PeerID
			if solanaWallet != nil {
				existing.SolanaWallet = solanaWallet
			}
			existing.PayoutWallet = pairing.PayoutWallet
			if payoutProofMessage != "" && payoutProofSignature != "" {
				existing.WorkerPayoutProofMessage = payoutProofMessage
				existing.WorkerPayoutProofSignature = payoutProofSignature
			}
			existing.LinkedAt = now
			if err := tx.Save(&existing).Error; err != nil {
				return err
			}
			linked = existing
			return nil
		}
		linked = models.UserDevice{
			UserID: pairing.UserID, NodeID: req.NodeID, PeerID: req.PeerID,
			SolanaWallet: solanaWallet, PayoutWallet: pairing.PayoutWallet,
			WorkerPayoutProofMessage: payoutProofMessage,
			WorkerPayoutProofSignature: payoutProofSignature,
			LinkedAt: now,
		}
		return tx.Create(&linked).Error
	})
	if err != nil {
		switch err.Error() {
		case "pairing_code_invalid":
			writeAuthJSON(w, http.StatusUnauthorized, map[string]string{"message": "Le code d’association est invalide ou déjà utilisé."})
		case "pairing_code_expired":
			writeAuthJSON(w, http.StatusGone, map[string]string{"message": "Le code d’association a expiré. Générez-en un nouveau."})
		case "pairing_code_node_mismatch":
			writeAuthJSON(w, http.StatusConflict, map[string]string{"message": "Ce code est destiné à une autre machine."})
		case "pairing_wallet_proof_required":
			writeAuthJSON(w, http.StatusConflict, map[string]string{"message": "Cette machine doit prouver le contrôle de son wallet de récompenses."})
		case "pairing_payout_wallet_invalid":
			writeAuthJSON(w, http.StatusConflict, map[string]string{"message": "Le wallet de récompense lié au code est invalide. Générez un nouveau code."})
		case "pairing_payout_wallet_mismatch":
			writeAuthJSON(w, http.StatusConflict, map[string]string{"message": "La preuve de la machine ne vise pas le wallet de ce compte."})
		case "device_binding_conflict":
			writeAuthJSON(w, http.StatusConflict, map[string]string{"message": "Ce code a déjà été utilisé pour une autre liaison de machine ou de wallet."})
		case "device_wallet_conflict", "worker_wallet_already_linked":
			writeAuthJSON(w, http.StatusConflict, map[string]string{"message": "Le wallet de cette machine est déjà lié à une autre identité."})
		case "device_already_linked":
			writeAuthJSON(w, http.StatusConflict, map[string]string{"message": "Cet appareil est déjà associé à un autre compte."})
		case "device_identity_conflict":
			writeAuthJSON(w, http.StatusConflict, map[string]string{"message": "Les identités de cet appareil correspondent à plusieurs associations existantes."})
		default:
			if errors.Is(err, gorm.ErrDuplicatedKey) {
				writeAuthJSON(w, http.StatusConflict, map[string]string{"message": "Une identité ou un wallet de cette machine est déjà associé."})
				return
			}
			writeAuthJSON(w, http.StatusInternalServerError, map[string]string{"message": "L’appareil n’a pas pu être associé."})
		}
		return
	}
	if directPairingNodeID != "" {
		_ = clearMiniworkerPairingCode(strings.TrimSpace(os.Getenv("SILICIUM_DEVICE_PAIRING_DIR")), directPairingNodeID)
	}
	w.Header().Set("Cache-Control", "no-store")
	writeAuthJSON(w, http.StatusOK, map[string]any{"device": linked})
}

func (h *Handler) UnlinkUserDevice(w http.ResponseWriter, r *http.Request) {
	userID, ok := userIDFromRequest(r)
	if !ok {
		writeAuthJSON(w, http.StatusUnauthorized, map[string]string{"message": "La session n’est pas valide."})
		return
	}
	id, err := strconv.ParseUint(strings.TrimSpace(mux.Vars(r)["id"]), 10, 64)
	if err != nil || id == 0 {
		writeAuthJSON(w, http.StatusBadRequest, map[string]string{"message": "L’identifiant de l’appareil est invalide."})
		return
	}
	result := h.DB.WithContext(r.Context()).Where("id = ? AND user_id = ?", id, userID).Delete(&models.UserDevice{})
	if result.Error != nil {
		writeAuthJSON(w, http.StatusInternalServerError, map[string]string{"message": "L’appareil n’a pas pu être dissocié."})
		return
	}
	if result.RowsAffected == 0 {
		writeAuthJSON(w, http.StatusNotFound, map[string]string{"message": "Cet appareil n’appartient pas à ce compte."})
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

func devicePairingPayload(code, nodeID, peerID string) []byte {
	return []byte(fmt.Sprintf("silicium-device-link-v1\n%s\n%s\n%s", code, nodeID, peerID))
}

func devicePairingWalletPayload(code, nodeID, peerID, solanaWallet string) []byte {
	return []byte(fmt.Sprintf("silicium-device-link-v2\n%s\n%s\n%s\n%s", code, nodeID, peerID, solanaWallet))
}

func devicePairingPayoutPayload(code, nodeID, peerID, solanaWallet, payoutWallet string) []byte {
	return []byte(fmt.Sprintf("silicium-device-payout-v1\n%s\n%s\n%s\n%s\n%s", code, nodeID, peerID, solanaWallet, payoutWallet))
}

func verifiedPayoutWallet(db *gorm.DB, userID uint) (*string, error) {
	var user models.User
	if err := db.Select("wallet_address").First(&user, userID).Error; err != nil || user.WalletAddress == nil {
		return nil, errors.New("verified wallet is missing")
	}
	wallet := strings.TrimSpace(*user.WalletAddress)
	if _, err := validateWalletAddress(wallet); err != nil {
		return nil, errors.New("verified wallet is invalid")
	}
	return &wallet, nil
}

func sameWallet(a, b *string) bool {
	if a == nil || b == nil {
		return a == nil && b == nil
	}
	return strings.TrimSpace(*a) == strings.TrimSpace(*b)
}

func devicePairingCodeHash(code string) string {
	digest := sha256.Sum256([]byte(code))
	return hex.EncodeToString(digest[:])
}

func writeMiniworkerPairingCode(root, nodeID, code, payoutWallet string) error {
	if !miniworkerNodeIDPattern.MatchString(nodeID) {
		return errors.New("miniworker_node_id_invalid")
	}
	dir := filepath.Join(root, nodeID)
	info, err := os.Stat(dir)
	if err != nil || !info.IsDir() {
		return errors.New("miniworker_pairing_directory_missing")
	}
	temporary, err := os.CreateTemp(dir, ".pairing-*")
	if err != nil {
		return err
	}
	name := temporary.Name()
	defer os.Remove(name)
	if err := temporary.Chmod(0640); err != nil {
		_ = temporary.Close()
		return err
	}
	if _, err := fmt.Fprintf(temporary, "%s\n%s\n", code, strings.TrimSpace(payoutWallet)); err != nil {
		_ = temporary.Close()
		return err
	}
	if err := temporary.Sync(); err != nil {
		_ = temporary.Close()
		return err
	}
	if err := temporary.Close(); err != nil {
		return err
	}
	return os.Rename(name, filepath.Join(dir, "device-pairing-code"))
}

func clearMiniworkerPairingCode(root, nodeID string) error {
	if !filepath.IsAbs(root) || !miniworkerNodeIDPattern.MatchString(nodeID) {
		return nil
	}
	err := os.Remove(filepath.Join(root, nodeID, "device-pairing-code"))
	if errors.Is(err, os.ErrNotExist) {
		return nil
	}
	return err
}
