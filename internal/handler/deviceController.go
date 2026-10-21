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

type pairDeviceRequest struct {
	Code            string `json:"code"`
	NodeID          string `json:"nodeId"`
	PeerID          string `json:"peerId"`
	PublicKey       string `json:"publicKey"`
	Signature       string `json:"signature"`
	SolanaWallet    string `json:"solanaWallet"`
	SolanaSignature string `json:"solanaSignature"`
}

type devicePairingCodesRequest struct {
	NodeIDs []string `json:"nodeIds"`
}

type devicePairingCodeResponse struct {
	NodeID    string    `json:"nodeId"`
	Code      string    `json:"code"`
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
	writeAuthJSON(w, http.StatusOK, map[string]any{"items": devices})
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
// requested miniworker IDs. This lets a user authorize a whole private worker
// pool without putting an account session token in any container.
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
	var req devicePairingCodesRequest
	if err := json.NewDecoder(http.MaxBytesReader(w, r.Body, 16<<10)).Decode(&req); err != nil || len(req.NodeIDs) < 1 || len(req.NodeIDs) > 24 {
		writeAuthJSON(w, http.StatusBadRequest, map[string]string{"message": "La liste des machines doit contenir entre 1 et 24 identifiants."})
		return
	}
	seen := make(map[string]struct{}, len(req.NodeIDs))
	items := make([]devicePairingCodeResponse, 0, len(req.NodeIDs))
	rows := make([]models.DevicePairingCode, 0, len(req.NodeIDs))
	now := time.Now().UTC()
	for _, rawNodeID := range req.NodeIDs {
		nodeID := strings.TrimSpace(rawNodeID)
		if !deviceNodeIDPattern.MatchString(nodeID) {
			writeAuthJSON(w, http.StatusBadRequest, map[string]string{"message": "Un identifiant de machine est invalide."})
			return
		}
		if _, exists := seen[nodeID]; exists {
			writeAuthJSON(w, http.StatusBadRequest, map[string]string{"message": "La liste contient un identifiant de machine en double."})
			return
		}
		seen[nodeID] = struct{}{}
		secret := make([]byte, 32)
		if _, err := rand.Read(secret); err != nil {
			writeAuthJSON(w, http.StatusInternalServerError, map[string]string{"message": "Les codes d’association ne peuvent pas être créés."})
			return
		}
		code := hex.EncodeToString(secret)
		digest := sha256.Sum256([]byte(code))
		expiresAt := now.Add(devicePairingLifetime)
		items = append(items, devicePairingCodeResponse{NodeID: nodeID, Code: code, ExpiresAt: expiresAt})
		rows = append(rows, models.DevicePairingCode{UserID: userID, NodeID: nodeID, PayoutWallet: payoutWallet, CodeHash: hex.EncodeToString(digest[:]), ExpiresAt: expiresAt})
	}
	err = h.DB.WithContext(r.Context()).Transaction(func(tx *gorm.DB) error {
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
		writeAuthJSON(w, http.StatusInternalServerError, map[string]string{"message": "Les codes d’association ne peuvent pas être enregistrés."})
		return
	}
	w.Header().Set("Cache-Control", "no-store")
	writeAuthJSON(w, http.StatusCreated, map[string]any{"items": items})
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
	if req.SolanaWallet != "" || req.SolanaSignature != "" {
		req.SolanaWallet = strings.TrimSpace(req.SolanaWallet)
		wallet, walletErr := validateWalletAddress(req.SolanaWallet)
		walletSignature, signatureErr := hex.DecodeString(strings.TrimSpace(req.SolanaSignature))
		if walletErr != nil || signatureErr != nil || len(walletSignature) != ed25519.SignatureSize {
			writeAuthJSON(w, http.StatusBadRequest, map[string]string{"message": "La preuve du portefeuille du worker est invalide."})
			return
		}
		pairingPayload = devicePairingWalletPayload(req.Code, req.NodeID, req.PeerID, req.SolanaWallet)
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
	err = h.DB.WithContext(r.Context()).Transaction(func(tx *gorm.DB) error {
		var pairing models.DevicePairingCode
		if err := tx.Where("code_hash = ?", codeHash).First(&pairing).Error; err != nil {
			return errors.New("pairing_code_invalid")
		}
		if pairing.NodeID != "" && pairing.NodeID != req.NodeID {
			return errors.New("pairing_code_node_mismatch")
		}
		if pairing.NodeID != "" && (solanaWallet == nil || pairing.PayoutWallet == nil || strings.TrimSpace(*pairing.PayoutWallet) == "") {
			return errors.New("pairing_wallet_proof_required")
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
			existing.LinkedAt = now
			if err := tx.Save(&existing).Error; err != nil {
				return err
			}
			linked = existing
			return nil
		}
		linked = models.UserDevice{UserID: pairing.UserID, NodeID: req.NodeID, PeerID: req.PeerID, SolanaWallet: solanaWallet, PayoutWallet: pairing.PayoutWallet, LinkedAt: now}
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
